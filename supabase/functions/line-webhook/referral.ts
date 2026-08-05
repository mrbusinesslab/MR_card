// 依 LINE userId 產生一組固定、6 碼的推薦碼（同一個人每次算出來都一樣）
export function generateReferralCode(userId: string): string {
  let hash = 0;
  for (let i = 0; i < userId.length; i++) {
    hash = (hash * 31 + userId.charCodeAt(i)) >>> 0;
  }
  return hash.toString(36).toUpperCase().padStart(6, '0').slice(-6);
}
