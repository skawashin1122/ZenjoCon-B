// 教員の承認画面
document.querySelectorAll(".approval").forEach((card) => {
  const id = card.dataset.student;
  const q = (sel) => card.querySelector(sel);

  function update(st) {
    q('[data-check="parent_consent"]').checked = st.parent_consent;
    q('[data-check="school_permission"]').checked = st.school_permission;
    const both = st.parent_consent && st.school_permission;
    q("[data-approve]").hidden = !both || st.approved;
    q("[data-revoke]").hidden = !st.approved;
    q("[data-wait]").hidden = both;
    q("[data-state]").textContent = st.approved ? "✓ 承認済み" : "― 未承認";
  }

  card.querySelectorAll("[data-check]").forEach((box) =>
    box.addEventListener("change", async () => {
      const st = await skima.send(`/api/teacher/students/${id}/checks`, "POST", {
        parent_consent: q('[data-check="parent_consent"]').checked,
        school_permission: q('[data-check="school_permission"]').checked,
      });
      if (st) update(st);
      else box.checked = !box.checked; // 失敗したら元に戻す
    })
  );
  q("[data-approve]").addEventListener("click", async () => {
    const st = await skima.send(`/api/teacher/students/${id}/approve`);
    if (st) update(st);
  });
  q("[data-revoke]").addEventListener("click", async () => {
    if (!confirm("承認を取り消しますか？ この生徒には求人が届かなくなります。")) return;
    const st = await skima.send(`/api/teacher/students/${id}/revoke`);
    if (st) update(st);
  });
});
