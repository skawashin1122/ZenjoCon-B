// 全画面で使う小さな道具
window.skima = {
  esc(s) {
    return String(s ?? "").replace(/[&<>"']/g, (c) => ({ "&": "&amp;", "<": "&lt;", ">": "&gt;", '"': "&quot;", "'": "&#39;" })[c]);
  },
  showError(msg) {
    const el = document.getElementById("error-msg");
    el.textContent = "⚠ " + msg;
    el.hidden = false;
    clearTimeout(el._t);
    el._t = setTimeout(() => (el.hidden = true), 6000);
  },
  // JSONを送って、結果を受け取る。失敗したらメッセージを表示して null を返す
  async send(url, method = "POST", body = null) {
    try {
      const res = await fetch(url, {
        method,
        headers: body ? { "Content-Type": "application/json" } : {},
        body: body ? JSON.stringify(body) : null,
      });
      const data = await res.json().catch(() => ({}));
      if (!res.ok) throw new Error(typeof data.detail === "string" ? data.detail : "うまくいきませんでした");
      return data;
    } catch (e) {
      this.showError(e.message === "Failed to fetch" ? "電波が弱いようです。もう一度お試しください。" : e.message);
      return null;
    }
  },
};
