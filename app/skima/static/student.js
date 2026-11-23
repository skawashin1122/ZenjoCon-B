// 高校生の画面：参加する・キャンセル・空き時間の登録
document.querySelectorAll("[data-confirm]").forEach((btn) =>
  btn.addEventListener("click", async () => {
    btn.disabled = true;
    const r = await skima.send(`/api/applications/${btn.dataset.confirm}/confirm`);
    if (r) location.reload();
    else btn.disabled = false;
  })
);

document.querySelectorAll("[data-cancel]").forEach((btn) =>
  btn.addEventListener("click", async () => {
    if (!confirm("参加をキャンセルしますか？ 生産者さんにお知らせが届きます。")) return;
    const r = await skima.send(`/api/applications/${btn.dataset.cancel}/cancel`);
    if (r) location.reload();
  })
);

document.querySelectorAll("[data-del]").forEach((btn) =>
  btn.addEventListener("click", async () => {
    const r = await skima.send("/api/me/slots", "DELETE", JSON.parse(btn.dataset.del));
    if (r) location.reload();
  })
);

const form = document.getElementById("slot-form");
if (form) {
  form.date.min = new Date().toLocaleDateString("sv-SE"); // 今日（YYYY-MM-DD・日本時間）
  form.addEventListener("submit", async (e) => {
    e.preventDefault();
    const r = await skima.send("/api/me/slots", "POST", {
      date: form.date.value, start: form.start.value, end: form.end.value,
    });
    if (r) location.reload();
  });
}
