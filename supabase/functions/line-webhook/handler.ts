import {
  ensureSession,
  updateSession,
  saveDiagnosisResult,
  getSessionByReferralCode,
  incrementReferralCount,
} from './session.ts';
import { textMessage, buildQuestionFlex, buildResultFlex, buildReferralMessage } from './line-messages.ts';
import { replyMessage } from './line-api.ts';
import { TRIGGER_KEYWORD, CONSULT_KEYWORD, ITEMS } from './questions.ts';
import { scoreByCategory } from './diagnosis.ts';
import { TIPS } from '../_shared/tips.ts';

const WELCOME_MESSAGE =
  '哈囉！我是品牌診斷小幫手 🙋\n想快速了解自己目前的品牌現況嗎？\n\n請直接輸入「初步診斷」四個字，就可以開始 1 分鐘診斷測驗 ✨';

const QUIZ_START_MESSAGE = '初步診斷開始！接下來7題，每題選一個最符合的程度就好。';

const CONSULT_REPLY =
  '已經收到你想預約一對一診斷諮詢的訊息了 🙌\n我們這邊會直接在這個對話裡跟你聯繫，也可以先跟我們說說你目前最卡關的地方，我們先幫你看看方向。';

const IDLE_HINT = `輸入「${TRIGGER_KEYWORD}」就可以開始品牌診斷測驗囉 ✨`;

// 轉介訊息開關：Supabase secrets 設 ENABLE_REFERRAL=true 才會在診斷完成後多送一則轉介訊息，預設關閉
const ENABLE_REFERRAL = Deno.env.get('ENABLE_REFERRAL') === 'true';

export async function handleEvent(event: any) {
  const userId = event.source?.userId;
  const replyToken = event.replyToken;
  if (!userId || !replyToken) return;

  let messages: unknown[] = [];

  if (event.type === 'follow') {
    messages = await handleFollow(userId);
  } else if (event.type === 'message' && event.message?.type === 'text') {
    messages = await handleTextMessage(userId, event.message.text);
  } else if (event.type === 'postback') {
    messages = await handlePostback(userId, event.postback.data);
  } else {
    return;
  }

  if (messages.length === 0) return;
  await replyMessage(replyToken, messages);
}

async function handleFollow(userId: string) {
  await ensureSession(userId);
  return [textMessage(WELCOME_MESSAGE)];
}

async function handleTextMessage(userId: string, text: string) {
  const { session, isNewUser } = await ensureSession(userId);
  const trimmed = text.trim();

  // 支援「初步診斷」或「初步診斷 推薦碼」兩種格式，任何時候輸入都會（重新）啟動診斷流程
  const parts = trimmed.split(/\s+/);
  if (parts[0] === TRIGGER_KEYWORD) {
    const refCode = parts[1];
    if (isNewUser && refCode && refCode !== session.referral_code && !session.referred_by) {
      const referrer = await getSessionByReferralCode(refCode);
      if (referrer && referrer.user_id !== userId) {
        await updateSession(userId, { referred_by: refCode });
        await incrementReferralCount(referrer.user_id);
      }
    }
    await updateSession(userId, { state: 'QUIZ', quiz_index: 0, quiz_answers: {} });
    return [textMessage(QUIZ_START_MESSAGE), buildQuestionFlex(0)];
  }

  // CTA 按鈕點擊後會送出這句話，不論目前在哪個狀態都直接回覆並標記為已諮詢
  if (trimmed === CONSULT_KEYWORD) {
    await updateSession(userId, { consulted: true, consulted_at: new Date().toISOString() });
    return [textMessage(CONSULT_REPLY)];
  }

  // 剛看完某則小技巧的完整內容、邀請對方練習寫下答案 —— 這裡接住那句回覆，給一個簡短鼓勵
  if (session.state === 'TIP_REFLECT') {
    await updateSession(userId, { state: 'IDLE' });
    return [
      textMessage('這個練習很不錯 👏 試著這週找一個實際的場合用用看，會比只是想過一遍更有感覺！'),
      textMessage(IDLE_HINT),
    ];
  }

  if (session.state === 'QUIZ') {
    return [textMessage('請直接點擊上面的選項按鈕作答喔 👆')];
  }

  return [textMessage(IDLE_HINT)];
}

async function handlePostback(userId: string, data: string) {
  const params = new URLSearchParams(data);
  const action = params.get('action');
  const { session } = await ensureSession(userId);

  if (action === 'quiz_answer') {
    const qId = Number(params.get('q'));
    const rawVal = params.get('val');
    const val = rawVal === 'null' || rawVal === null ? null : Number(rawVal);

    const answers = { ...(session.quiz_answers || {}), [qId]: val };
    const nextIndex = session.quiz_index + 1;

    if (nextIndex < ITEMS.length) {
      await updateSession(userId, { quiz_answers: answers, quiz_index: nextIndex });
      return [buildQuestionFlex(nextIndex)];
    }

    // 最後一題，產生診斷結果
    await updateSession(userId, {
      quiz_answers: answers,
      quiz_index: nextIndex,
      state: 'DONE',
      diagnosis_completed_at: new Date().toISOString(),
    });

    const scored = scoreByCategory(answers);
    const worstCategory = scored.length > 0 ? scored[0].cat : null;
    const overallPct = scored.length > 0 ? Math.round(scored.reduce((s, c) => s + c.pct, 0) / scored.length) : null;

    await saveDiagnosisResult({ userId, worstCategory, overallPct, answers });

    const referralCode = session.referral_code ?? '';
    const resultMessages: unknown[] = [buildResultFlex(answers)];
    if (ENABLE_REFERRAL) {
      resultMessages.push(buildReferralMessage(referralCode));
    }
    return resultMessages;
  }

  if (action === 'request_consult') {
    await updateSession(userId, { consulted: true, consulted_at: new Date().toISOString() });
    return [textMessage(CONSULT_REPLY)];
  }

  if (action === 'tip_detail') {
    const idx = Number(params.get('idx'));
    const tip = TIPS[idx];
    if (!tip) return [];
    await updateSession(userId, { state: 'TIP_REFLECT' });
    return [textMessage(`${tip.fullTitle}\n\n${tip.fullBody}`)];
  }

  return [];
}
