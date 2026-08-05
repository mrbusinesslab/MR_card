// MR. business.lab 初步診斷 —— 單題漸進式（4 點量表）診斷資料

export const TRIGGER_KEYWORD = '初步診斷';
export const CONSULT_KEYWORD = '預約諮詢';

export const NUMBER_SYMBOLS = ['➊', '➋', '➌', '➍', '➎', '➏', '➐'];

export interface ScaleOption {
  label: string;
  value: number | null;
}

export const SCALE: ScaleOption[] = [
  { label: '非常有感', value: 100 },
  { label: '有一點', value: 66 },
  { label: '還好', value: 33 },
  { label: '不是我的情況', value: null },
];

export const CATEGORIES: Record<string, { label: string }> = {
  trust: { label: '信任建立' },
  value: { label: '價值傳遞' },
  position: { label: '品牌定位' },
  digital: { label: '數位曝光' },
  referral: { label: '口碑轉介' },
};

export const CATEGORY_DESC: Record<string, string> = {
  trust: '目前最大的瓶頸在「信任建立」，客戶見面後仍猶豫不決，需要加強讓人願意放心成交的環節。',
  value: '目前最大的瓶頸在「價值傳遞」，報價容易被殺價，代表客戶還沒感受到你的專業值得這個價格。',
  position: '目前最大的瓶頸在「品牌定位」，還沒有一句話能清楚說明你是誰、為什麼該選你。',
  digital: '目前最大的瓶頸在「數位曝光」，客戶在線上找不到你，或找到的呈現不夠專業。',
  referral: '目前最大的瓶頸在「口碑轉介」，客戶滿意卻缺乏主動幫你介紹新客戶的動力。',
};

export interface QuizItem {
  id: number;
  text: string;
  cat: string;
}

export const ITEMS: QuizItem[] = [
  { id: 1, text: '見面後客戶仍「需要再想想」', cat: 'trust' },
  { id: 2, text: '報價後被殺價，感覺技術沒被尊重', cat: 'value' },
  { id: 3, text: '不知道怎麼30秒說清楚自己是誰', cat: 'position' },
  { id: 4, text: '不知道怎麼在社群上讓人看見我的專業', cat: 'digital' },
  { id: 5, text: '知道自己做什麼，但無法簡單有力說明「為什麼選我」', cat: 'position' },
  { id: 6, text: '客戶滿意，但很少主動介紹我給別人', cat: 'referral' },
  { id: 7, text: '線上搜不到我，或搜到的東西不像樣', cat: 'digital' },
];
