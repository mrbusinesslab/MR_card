const DEFAULT_CASE = "case1_小如如";
const CASE_PATTERN = /^case\d+_[A-Za-z0-9\u3400-\u9fff-]+$/u;
const requestedCase = new URLSearchParams(window.location.search).get("case") || DEFAULT_CASE;
const caseId = CASE_PATTERN.test(requestedCase) ? requestedCase : DEFAULT_CASE;
const [, ...nameParts] = caseId.split("_");
const personName = nameParts.join("_");
const CARD_JSON_URL = `../ai-MRbot/templates/${encodeURIComponent(caseId)}/card_${encodeURIComponent(personName)}.json`;

const viewport = document.querySelector("#cardViewport");
const dots = document.querySelector("#pageDots");
const status = document.querySelector("#actionStatus");

const versionDate = document.querySelector("#versionDate");
document.querySelector("#personName").textContent = personName;
document.querySelector("#avatar").textContent = [...personName.replace(/\s+/g, "")].at(-1) || "名";
document.title = `${personName}的電子名片｜MR BUSINESS LAB`;
document.querySelector('meta[name="description"]').content = `${personName}的專屬電子名片｜MR BUSINESS LAB`;

function setVersionDate(lastModified) {
  const parsed = lastModified ? new Date(lastModified) : new Date();
  const safeDate = Number.isNaN(parsed.getTime()) ? new Date() : parsed;
  versionDate.dateTime = safeDate.toISOString().slice(0, 10);
  versionDate.textContent = new Intl.DateTimeFormat("zh-TW", {
    timeZone: "Asia/Taipei",
    year: "numeric",
    month: "2-digit",
    day: "2-digit"
  }).format(safeDate);
}

function normalizeColor(value, fallback) {
  return /^#[0-9a-f]{6}$/i.test(value || "") ? value : fallback;
}

function readableText(hex) {
  const [r, g, b] = hex.slice(1).match(/.{2}/g).map((part) => parseInt(part, 16) / 255);
  const linear = [r, g, b].map((value) => value <= 0.03928 ? value / 12.92 : ((value + 0.055) / 1.055) ** 2.4);
  return 0.2126 * linear[0] + 0.7152 * linear[1] + 0.0722 * linear[2] > 0.48 ? "#1d1a18" : "#ffffff";
}

function applyTheme(page) {
  const nodes = allNodes(page);
  const actionNodes = nodes.filter((node) => node.action?.type === "uri" && node.action.uri);
  const surfaceNode = nodes.find((node) =>
    node.backgroundColor &&
    Array.isArray(node.contents) &&
    allNodes(node.contents).some((child) => child.action?.type === "uri")
  );
  const primary = normalizeColor(actionNodes[0]?.backgroundColor, "#1d1a18");
  const secondary = normalizeColor(actionNodes[1]?.backgroundColor, "#f7f3ed");
  const surface = normalizeColor(surfaceNode?.backgroundColor, secondary);
  const root = document.documentElement;
  root.style.setProperty("--theme-primary", primary);
  root.style.setProperty("--theme-secondary", secondary);
  root.style.setProperty("--theme-surface", surface);
  root.style.setProperty("--theme-on-primary", readableText(primary));
  document.querySelector("#themeColor").content = secondary;
}

async function getCardUpdatedAt(fallback) {
  const filePath = `ai-MRbot/templates/${caseId}/card_${personName}.json`;
  const apiUrl = `https://api.github.com/repos/mrbusinesslab/MR_card/commits?path=${encodeURIComponent(filePath)}&per_page=1`;
  try {
    const response = await fetch(apiUrl, { headers: { Accept: "application/vnd.github+json" } });
    if (!response.ok) throw new Error(`GitHub HTTP ${response.status}`);
    const commits = await response.json();
    return commits[0]?.commit?.committer?.date || commits[0]?.commit?.author?.date || fallback;
  } catch {
    return fallback;
  }
}

function allNodes(value) {
  if (!value || typeof value !== "object") return [];
  if (Array.isArray(value)) return value.flatMap(allNodes);
  return [value, ...Object.values(value).flatMap(allNodes)];
}

function getCardData(page) {
  const nodes = allNodes(page);
  const image = nodes.find((node) => node.type === "image" && node.url);
  const actions = nodes.filter((node) => node.action?.type === "uri" && node.action.uri);
  return {
    imageUrl: image?.url || "",
    buttons: actions.map((node) => {
      const label = allNodes(node).filter((item) => item.type === "text" && item.text).at(-1)?.text || "開啟連結";
      return {
        label,
        href: node.action.uri,
        background: node.backgroundColor || "#6d513e",
        color: allNodes(node).find((item) => item.type === "text" && item.color)?.color || "#ffffff",
        border: node.borderColor || node.backgroundColor || "#6d513e"
      };
    })
  };
}

function renderCard(flex) {
  const pages = Array.isArray(flex?.contents) ? flex.contents : [];
  if (!pages.length) throw new Error("名片內容為空");

  applyTheme(pages[0]);
  viewport.replaceChildren();
  dots.replaceChildren();

  pages.forEach((page, index) => {
    const data = getCardData(page);
    const section = document.createElement("section");
    section.className = "card-page";
    section.setAttribute("aria-label", `電子名片第 ${index + 1} 頁，共 ${pages.length} 頁`);

    const image = document.createElement("img");
    image.src = data.imageUrl;
    image.alt = `${personName}電子名片第 ${index + 1} 頁`;
    image.loading = index === 0 ? "eager" : "lazy";
    section.append(image);

    const buttonGroup = document.createElement("div");
    buttonGroup.className = "card-buttons";
    data.buttons.forEach((button) => {
      const link = document.createElement("a");
      link.className = "card-button";
      link.href = button.href;
      link.textContent = button.label;
      link.target = "_blank";
      link.rel = "noopener noreferrer";
      link.style.setProperty("--button-bg", button.background);
      link.style.setProperty("--button-text", button.color);
      link.style.setProperty("--button-color", button.border);
      buttonGroup.append(link);
    });
    section.append(buttonGroup);
    viewport.append(section);

    const dot = document.createElement("button");
    dot.type = "button";
    dot.className = `page-dot${index === 0 ? " is-active" : ""}`;
    dot.setAttribute("aria-label", `前往第 ${index + 1} 頁`);
    dot.addEventListener("click", () => section.scrollIntoView({ behavior: "smooth", inline: "start", block: "nearest" }));
    dots.append(dot);
  });

  const updateDot = () => {
    const activeIndex = Math.round(viewport.scrollLeft / viewport.clientWidth);
    dots.querySelectorAll(".page-dot").forEach((dot, index) => dot.classList.toggle("is-active", index === activeIndex));
  };
  viewport.addEventListener("scroll", updateDot, { passive: true });
}

async function loadCard() {
  const response = await fetch(CARD_JSON_URL, { cache: "no-store" });
  if (!response.ok) throw new Error(`HTTP ${response.status}`);
  const fallbackDate = response.headers.get("last-modified");
  const [card, updatedAt] = await Promise.all([
    response.json(),
    getCardUpdatedAt(fallbackDate)
  ]);
  setVersionDate(updatedAt);
  renderCard(card);
}

function showStatus(message, isError = false) {
  status.textContent = message;
  status.style.color = isError ? "#a7463d" : "#397251";
}

document.querySelector("#shareButton").addEventListener("click", async () => {
  const shareData = {
    title: `${personName}的電子名片`,
    text: `這是${personName}的專屬電子名片`,
    url: window.location.href
  };
  try {
    if (navigator.share) {
      await navigator.share(shareData);
      showStatus("已開啟分享選單");
    } else {
      await navigator.clipboard.writeText(window.location.href);
      showStatus("瀏覽器不支援分享選單，已複製專屬網址");
    }
  } catch (error) {
    if (error?.name !== "AbortError") showStatus("目前無法開啟分享功能，請改用複製網址", true);
  }
});

document.querySelector("#copyButton").addEventListener("click", async () => {
  try {
    await navigator.clipboard.writeText(window.location.href);
    showStatus("專屬網址已複製");
  } catch {
    showStatus("無法自動複製，請從瀏覽器網址列複製", true);
  }
});

loadCard().catch(() => {
  viewport.innerHTML = '<div class="loading-state">目前無法載入電子名片，請稍後再試。</div>';
});
