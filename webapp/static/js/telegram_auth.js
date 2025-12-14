(function () {
  if (!window.Telegram || !Telegram.WebApp) {
    console.warn("Telegram WebApp API not found");
    return;
  }

  const tg = Telegram.WebApp;
  tg.ready();

  if (!tg.initData || tg.initData.length === 0) {
    console.warn("No initData from Telegram");
    return;
  }

  fetch("/api/v1/auth/telegram-webapp", {
    method: "POST",
    headers: {
      "Content-Type": "application/json",
    },
    credentials: "include",
    body: JSON.stringify({
      init_data: tg.initData,
    }),
  })
    .then(async (resp) => {
      if (!resp.ok) {
        const txt = await resp.text();
        throw new Error(txt);
      }
      return resp.json();
    })
    .then((data) => {
      console.log("Telegram auth OK", data);
      // cookie user_id поставлена backend'ом
    })
    .catch((err) => {
      console.error("Telegram auth failed", err);
    });
})();
