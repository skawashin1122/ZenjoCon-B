// 生産者の画面：写真をとる → 話す → AIの下書きを確認 → 公開
(() => {
  const $ = (id) => document.getElementById(id);
  const MAX_SIDE = 1280;      // 写真の長い辺をこの大きさまで縮小（電波が弱い場所でも送れるように）
  const MAX_REC_SEC = 30;     // 録音は最長30秒

  let photoBlob = null;
  let currentJob = null;
  let startedAt = null; // 試用テストの計測：最初にボタンを押した時刻

  // 「写真をとる」「話して伝える」のどちらかを最初に押した時刻を覚える
  for (const id of ["btn-photo", "btn-talk"]) {
    $(id).addEventListener("click", () => { startedAt ??= Date.now(); }, { capture: true });
  }

  // ---------- 画面の切り替え ----------
  function show(step) {
    for (const s of ["home", "loading", "draft", "done"]) $("step-" + s).hidden = s !== step;
    $("error-msg").hidden = true;
  }
  function showError(msg) {
    $("error-msg").textContent = "⚠ " + msg;
    $("error-msg").hidden = false;
    speak(msg);
  }

  // ---------- 読み上げ ----------
  function speak(text) {
    if (!("speechSynthesis" in window) || !text) return;
    speechSynthesis.cancel();
    const u = new SpeechSynthesisUtterance(text);
    u.lang = "ja-JP";
    u.rate = 0.9; // 少しゆっくり
    speechSynthesis.speak(u);
  }

  // ---------- 写真：スマホ側で縮小してから送る ----------
  async function shrinkImage(file) {
    const bitmap = await createImageBitmap(file);
    const scale = Math.min(1, MAX_SIDE / Math.max(bitmap.width, bitmap.height));
    const canvas = document.createElement("canvas");
    canvas.width = Math.round(bitmap.width * scale);
    canvas.height = Math.round(bitmap.height * scale);
    canvas.getContext("2d").drawImage(bitmap, 0, 0, canvas.width, canvas.height);
    return new Promise((resolve) => canvas.toBlob(resolve, "image/jpeg", 0.8));
  }

  $("btn-photo").addEventListener("click", () => $("photo-input").click());
  $("photo-input").addEventListener("change", async (e) => {
    const file = e.target.files[0];
    if (!file) return;
    try {
      photoBlob = await shrinkImage(file);
    } catch {
      photoBlob = file; // 縮小できない形式はそのまま送る
    }
    $("photo-img").src = URL.createObjectURL(photoBlob);
    $("photo-preview").hidden = false;
  });

  // ---------- 録音：16kHz・モノラルのWAVに変換して送る ----------
  // （ブラウザごとに録音形式が違うため、どのブラウザでも同じWAV形式にそろえる）
  function createRecorder(button, label, labelIdle, onDone) {
    let recorder = null, chunks = [], timer = null, started = 0;

    async function start() {
      let stream;
      try {
        stream = await navigator.mediaDevices.getUserMedia({ audio: true });
      } catch {
        showError("マイクが使えません。マイクの使用を許可してください。");
        return;
      }
      chunks = [];
      recorder = new MediaRecorder(stream);
      recorder.ondataavailable = (e) => e.data.size && chunks.push(e.data);
      recorder.onstop = async () => {
        stream.getTracks().forEach((t) => t.stop());
        clearInterval(timer);
        button.classList.remove("recording");
        label.textContent = labelIdle;
        $("rec-status").hidden = true;
        const blob = new Blob(chunks, { type: recorder.mimeType });
        try {
          onDone(await toWav(blob));
        } catch {
          showError("録音を読み取れませんでした。もう一度話してください。");
        }
      };
      recorder.start();
      started = Date.now();
      button.classList.add("recording");
      label.textContent = "話し終わったら押す";
      $("rec-status").hidden = false;
      timer = setInterval(() => {
        const sec = Math.floor((Date.now() - started) / 1000);
        $("rec-status").textContent = `● 録音中 ${sec}秒`;
        if (sec >= MAX_REC_SEC) stop();
      }, 250);
    }
    function stop() {
      if (recorder && recorder.state === "recording") recorder.stop();
    }
    button.addEventListener("click", () => (recorder && recorder.state === "recording" ? stop() : start()));
  }

  async function toWav(blob) {
    const ctx = new AudioContext();
    const decoded = await ctx.decodeAudioData(await blob.arrayBuffer());
    ctx.close();
    const rate = 16000;
    const offline = new OfflineAudioContext(1, Math.ceil(decoded.duration * rate), rate);
    const src = offline.createBufferSource();
    src.buffer = decoded;
    src.connect(offline.destination);
    src.start();
    const samples = (await offline.startRendering()).getChannelData(0);

    const buf = new ArrayBuffer(44 + samples.length * 2);
    const v = new DataView(buf);
    const str = (o, s) => [...s].forEach((c, i) => v.setUint8(o + i, c.charCodeAt(0)));
    str(0, "RIFF"); v.setUint32(4, 36 + samples.length * 2, true); str(8, "WAVE");
    str(12, "fmt "); v.setUint32(16, 16, true); v.setUint16(20, 1, true); v.setUint16(22, 1, true);
    v.setUint32(24, rate, true); v.setUint32(28, rate * 2, true); v.setUint16(32, 2, true); v.setUint16(34, 16, true);
    str(36, "data"); v.setUint32(40, samples.length * 2, true);
    samples.forEach((s, i) => v.setInt16(44 + i * 2, Math.max(-1, Math.min(1, s)) * 0x7fff, true));
    return new Blob([buf], { type: "audio/wav" });
  }

  // ---------- サーバーとのやりとり ----------
  async function post(url, form) {
    show("loading");
    try {
      const res = await fetch(url, { method: "POST", body: form });
      const data = await res.json().catch(() => ({}));
      if (!res.ok) throw new Error(data.detail || "うまくいきませんでした。もう一度お試しください。");
      return data;
    } catch (e) {
      show(currentJob ? "draft" : "home");
      showError(e.message === "Failed to fetch" ? "電波が弱いようです。もう一度お試しください。" : e.message);
      return null;
    }
  }

  createRecorder($("btn-talk"), $("talk-label"), "話して伝える", async (wav) => {
    const form = new FormData();
    if (photoBlob) form.append("photo", photoBlob, "photo.jpg");
    form.append("audio", wav, "voice.wav");
    currentJob = null;
    const data = await post("/api/drafts", form);
    if (data) renderDraft(data);
  });

  createRecorder($("btn-answer"), $("answer-label"), "話して答える", async (wav) => {
    const form = new FormData();
    form.append("audio", wav, "answer.wav");
    const data = await post(`/api/jobs/${currentJob.job_id}/answer`, form);
    if (data) renderDraft(data);
  });

  // ---------- 下書きの表示 ----------
  const esc = (s) => String(s ?? "").replace(/[&<>"']/g, (c) => ({ "&": "&amp;", "<": "&lt;", ">": "&gt;", '"': "&quot;", "'": "&#39;" })[c]);
  const val = (v, suffix = "") => (v === null || v === undefined || v === "" ? '<span class="missing">？ まだ</span>' : esc(v) + suffix);
  const PLACE = { land: "陸上の作業", boat: "船の上の作業", unknown: null };

  function renderDraft(data) {
    currentJob = data;
    const d = data.draft;
    $("draft-card").innerHTML = `
      <h1 class="job-title">${val(d.title)}</h1>
      ${d.description ? `<p>${esc(d.description)}</p>` : ""}
      <dl class="facts">
        <dt>日にち</dt><dd>${d.work_date ? esc(data.display.date) : val(null)}</dd>
        <dt>時間</dt><dd>${d.start_time && d.end_time ? esc(data.display.time) : val(null)}</dd>
        <dt>人数</dt><dd>${val(d.headcount, "人")}</dd>
        <dt>時給</dt><dd>${d.hourly_wage ? esc(d.hourly_wage.toLocaleString()) + "円" : val(null)}</dd>
        <dt>場所</dt><dd>${d.area ? esc(d.area) + "地区" : val(null)}（${PLACE[d.location_type] ? esc(PLACE[d.location_type]) : '<span class="missing">？ 陸か船か</span>'}）</dd>
        <dt>重さ</dt><dd>${d.max_weight_kg != null ? "1回 約" + esc(d.max_weight_kg) + "kg" : val(null)}</dd>
      </dl>
      ${d.items.length ? `<p><strong>持ち物：</strong>${d.items.map(esc).join("・")}</p>` : ""}
      ${d.cautions.length ? `<ul class="cautions">${d.cautions.map((c) => `<li>⚠ ${esc(c)}</li>`).join("")}</ul>` : ""}`;

    $("draft-errors").hidden = !data.errors.length;
    $("draft-errors").innerHTML = data.errors.map((e) => "⚠ " + esc(e)).join("<br>");

    // 足りない項目があるときは、その項目だけを聞き直す
    const needAnswer = !!data.question || data.errors.length > 0;
    $("draft-question").hidden = !needAnswer;
    $("question-text").textContent = data.question || "上の ⚠ の内容を、声で言い直してください。";

    $("btn-publish").disabled = !data.can_publish;
    show("draft");
    speak(data.speech);
  }

  $("btn-speak").addEventListener("click", () => currentJob && speak(currentJob.speech));

  $("btn-publish").addEventListener("click", async () => {
    const form = new FormData();
    if (startedAt) form.append("client_seconds", ((Date.now() - startedAt) / 1000).toFixed(1));
    const data = await post(`/api/jobs/${currentJob.job_id}/publish`, form);
    if (!data) return;
    $("done-link").href = data.url;
    $("survey-link").href = `/survey/${data.job_id}`;
    if (!data.visible_to_high_school) {
      $("done-note").textContent = "この作業は高校生には案内しません（" + data.high_school_blockers.join("・") + "）。";
    } else if (data.offered > 0) {
      $("done-note").textContent = `条件に合う高校生${data.offered}人に案内を送りました。参加が決まったらお知らせします。`;
    } else {
      $("done-note").textContent = "いま条件に合う高校生がいません（承認・空き時間・場所の条件）。";
    }
    show("done");
    speak("公開しました。" + $("done-note").textContent);
  });

  function reset() {
    currentJob = null;
    photoBlob = null;
    startedAt = null;
    $("photo-input").value = "";
    $("photo-preview").hidden = true;
    show("home");
  }
  // ---------- はじめて使う人への案内（3枚） ----------
  // 見たかどうかはこのスマホの中だけに覚える（使えない環境では毎回出さない）
  const ONBOARD_KEY = "skima_onboarded";
  let onboardStep = 0;
  function showOnboardStep(i) {
    onboardStep = i;
    document.querySelectorAll(".onboard-step").forEach((el) => (el.hidden = Number(el.dataset.step) !== i));
    document.querySelectorAll(".onboard-dots span").forEach((el, k) => el.classList.toggle("on", k === i));
    $("onboard-next").textContent = i === 2 ? "はじめる" : "つぎへ";
    $("onboard-next").focus();
  }
  function openOnboard() { $("onboard").hidden = false; showOnboardStep(0); }
  function closeOnboard() {
    $("onboard").hidden = true;
    try { localStorage.setItem(ONBOARD_KEY, "1"); } catch {}
  }
  $("onboard-next").addEventListener("click", () => (onboardStep < 2 ? showOnboardStep(onboardStep + 1) : closeOnboard()));
  $("onboard-skip").addEventListener("click", closeOnboard);
  $("btn-howto").addEventListener("click", openOnboard);
  let seen = true;
  try { seen = localStorage.getItem(ONBOARD_KEY) === "1"; } catch {}
  if (!seen) openOnboard();

  $("btn-retry").addEventListener("click", reset);
  $("btn-new").addEventListener("click", () => location.reload()); // 求人の一覧も新しくする
})();
