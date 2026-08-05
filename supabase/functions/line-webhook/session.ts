import { createClient } from 'npm:@supabase/supabase-js@2';
import { generateReferralCode } from './referral.ts';

const supabase = createClient(
  Deno.env.get('SUPABASE_URL')!,
  Deno.env.get('SUPABASE_SERVICE_ROLE_KEY')!,
);

export interface Session {
  user_id: string;
  state: string; // 'IDLE' | 'QUIZ' | 'DONE'
  quiz_index: number;
  quiz_answers: Record<number, number | null>;
  consulted: boolean;
  consulted_at: string | null;
  diagnosis_completed_at: string | null;
  followup_sent_at: string | null;
  referral_code: string | null;
  referred_by: string | null;
  referral_count: number;
}

export async function getSession(userId: string): Promise<Session | null> {
  const { data, error } = await supabase.from('line_sessions').select('*').eq('user_id', userId).maybeSingle();
  if (error) throw error;
  return data as Session | null;
}

export async function createSession(userId: string): Promise<Session> {
  const { data, error } = await supabase
    .from('line_sessions')
    .insert({ user_id: userId, state: 'IDLE', quiz_index: 0, quiz_answers: {}, referral_code: generateReferralCode(userId) })
    .select()
    .single();
  if (error) throw error;
  return data as Session;
}

export async function updateSession(userId: string, patch: Partial<Session>): Promise<Session> {
  const { data, error } = await supabase
    .from('line_sessions')
    .update({ ...patch, updated_at: new Date().toISOString() })
    .eq('user_id', userId)
    .select()
    .single();
  if (error) throw error;
  return data as Session;
}

// 取得 session，不存在就建立；如果是舊資料還沒有 referral_code，順便補上
export async function ensureSession(userId: string): Promise<{ session: Session; isNewUser: boolean }> {
  let session = await getSession(userId);
  const isNewUser = !session;
  if (!session) {
    session = await createSession(userId);
  } else if (!session.referral_code) {
    session = await updateSession(userId, { referral_code: generateReferralCode(userId) });
  }
  return { session, isNewUser };
}

export async function getSessionByReferralCode(code: string): Promise<Session | null> {
  const { data, error } = await supabase.from('line_sessions').select('*').eq('referral_code', code).maybeSingle();
  if (error) throw error;
  return data as Session | null;
}

export async function incrementReferralCount(userId: string): Promise<void> {
  const session = await getSession(userId);
  if (!session) return;
  await updateSession(userId, { referral_count: (session.referral_count ?? 0) + 1 });
}

export async function saveDiagnosisResult(params: {
  userId: string;
  worstCategory: string | null;
  overallPct: number | null;
  answers: Record<number, number | null>;
}) {
  const { error } = await supabase.from('line_diagnosis_results').insert({
    user_id: params.userId,
    primary_category: params.worstCategory,
    selected_tags: null,
    answers: { overall_pct: params.overallPct, quiz_answers: params.answers },
  });
  if (error) throw error;
}
