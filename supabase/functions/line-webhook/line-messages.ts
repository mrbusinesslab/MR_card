import { ITEMS, NUMBER_SYMBOLS, SCALE, CONSULT_KEYWORD } from './questions.ts';
import { CATEGORY_DESC } from './questions.ts';
import { scoreByCategory, ScoredCategory } from './diagnosis.ts';

export function textMessage(text: string) {
  return { type: 'text', text };
}

// 品牌色（跟你提供的範例一致）
const BRAND_CREAM = '#F7F1E6';
const BRAND_BLACK = '#17140F';
const BRAND_GOLD = '#C9A961';
const BAR_TRACK = '#3a372e';
const BAR_CARD_INNER = '#221f18';

// CTA 按鈕：用 message 類型，點擊後會在聊天室送出「預約諮詢」這句話，
// 由 handler.ts 偵測這個關鍵字接手回覆，全程不會跳轉外部連結
function buildCtaAction() {
  return {
    type: 'message',
    label: '預約一對一診斷諮詢',
    text: CONSULT_KEYWORD,
  };
}

// index 為 0-based，對應 ITEMS 裡的第幾題
export function buildQuestionFlex(index: number) {
  const item = ITEMS[index];
  const number = NUMBER_SYMBOLS[index] ?? String(index + 1);

  const buttons = SCALE.map((opt) => {
    const valStr = opt.value === null ? 'null' : String(opt.value);
    return {
      type: 'box',
      layout: 'vertical',
      backgroundColor: '#FBF8F1',
      borderColor: '#5c4a35',
      borderWidth: 'medium',
      cornerRadius: '10px',
      paddingAll: '10px',
      action: {
        type: 'postback',
        label: opt.label,
        data: `action=quiz_answer&q=${item.id}&val=${valStr}`,
        displayText: opt.label,
      },
      contents: [
        { type: 'text', text: opt.label, align: 'center', wrap: true, size: 'md', weight: 'bold', color: '#3a2f22' },
      ],
    };
  });

  const footerRows = buttons;

  return {
    type: 'flex',
    altText: `${number} ${item.text}`,
    contents: {
      type: 'bubble',
      size: 'kilo',
      body: {
        type: 'box',
        layout: 'vertical',
        spacing: 'md',
        backgroundColor: BRAND_CREAM,
        paddingAll: '20px',
        contents: [
          { type: 'text', text: number, size: 'xl', weight: 'bold', color: BRAND_GOLD },
          { type: 'text', text: item.text, wrap: true, size: 'md', weight: 'bold', color: BRAND_BLACK, margin: 'sm' },
        ],
      },
      footer: {
        type: 'box',
        layout: 'vertical',
        spacing: 'sm',
        backgroundColor: BRAND_CREAM,
        paddingAll: '16px',
        contents: footerRows,
      },
    },
  };
}

function buildBarRow(label: string, pct: number) {
  return {
    type: 'box',
    layout: 'vertical',
    margin: 'md',
    spacing: 'sm',
    contents: [
      {
        type: 'box',
        layout: 'horizontal',
        contents: [
          { type: 'text', text: label, size: 'sm', color: BRAND_CREAM, flex: 4 },
          { type: 'text', text: `${pct}%`, size: 'sm', color: BRAND_GOLD, align: 'end', flex: 1 },
        ],
      },
      {
        type: 'box',
        layout: 'horizontal',
        height: '8px',
        cornerRadius: '4px',
        backgroundColor: BAR_TRACK,
        contents: [
          { type: 'box', layout: 'vertical', flex: pct, backgroundColor: BRAND_GOLD, cornerRadius: '4px', contents: [] },
          { type: 'box', layout: 'vertical', flex: Math.max(100 - pct, 0), contents: [] },
        ],
      },
    ],
  };
}

// answers: { [questionId: number]: number | null }
export function buildResultFlex(answers: Record<number, number | null>) {
  const scored: ScoredCategory[] = scoreByCategory(answers);

  if (scored.length === 0) {
    return textMessage('這次的回答都標記為「不是我的情況」，暫時無法產生診斷結果，建議挑至少一題勾選有感的程度再試一次。輸入「初步診斷」可以重新開始。');
  }

  const worstCat = scored[0].cat;
  const overall = Math.round(scored.reduce((sum, c) => sum + c.pct, 0) / scored.length);
  const barRows = scored.map((c) => buildBarRow(c.label, c.pct));

  return {
    type: 'flex',
    altText: `診斷結果：整體待改善指數 ${overall}%`,
    contents: {
      type: 'bubble',
      size: 'kilo',
      body: {
        type: 'box',
        layout: 'vertical',
        backgroundColor: BRAND_BLACK,
        paddingAll: '18px',
        spacing: 'md',
        contents: [
          { type: 'text', text: '診斷結果', size: 'xs', color: BRAND_GOLD, weight: 'bold' },
          { type: 'text', text: `整體待改善指數 ${overall}%`, size: 'xl', color: BRAND_CREAM, weight: 'bold', margin: 'xs' },
          { type: 'separator', color: BAR_TRACK, margin: 'md' },
          ...barRows,
          {
            type: 'box',
            layout: 'vertical',
            backgroundColor: BAR_CARD_INNER,
            cornerRadius: '8px',
            paddingAll: '12px',
            margin: 'lg',
            contents: [{ type: 'text', text: CATEGORY_DESC[worstCat], size: 'xs', color: BRAND_CREAM, wrap: true }],
          },
        ],
      },
      footer: {
        type: 'box',
        layout: 'vertical',
        backgroundColor: BRAND_BLACK,
        paddingAll: '12px',
        contents: [
          {
            type: 'button',
            style: 'primary',
            color: BRAND_GOLD,
            action: buildCtaAction(),
          },
        ],
      },
    },
  };
}

export function buildReferralMessage(referralCode: string) {
  return textMessage(
    `想邀請朋友一起測嗎？\n把這則訊息長按轉發給朋友，請他在對話框輸入：\n\n初步診斷 ${referralCode}\n\n他完成診斷後，我們也會知道是你推薦的 🙌`,
  );
}
