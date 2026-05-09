/**
 * Cloudflare Worker — Telegram Bot API 反向代理
 *
 * 将请求从 CF 边缘转发到 api.telegram.org，
 * 解决中国大陆服务器无法直连 Telegram 的问题。
 *
 * 环境变量（可选）：
 *   TCC_KEY — 设置后，请求必须携带 X-TCC-Key 头匹配才放行
 */

const TG_HOST = "api.telegram.org";

export default {
  async fetch(request, env) {
    // 可选鉴权
    if (env.TCC_KEY) {
      const key = request.headers.get("X-TCC-Key");
      if (key !== env.TCC_KEY) {
        return new Response("Unauthorized", { status: 403 });
      }
    }

    // 仅允许 Telegram Bot API 路径
    const url = new URL(request.url);
    if (!url.pathname.startsWith("/bot") && !url.pathname.startsWith("/file/bot")) {
      return new Response("Not Found", { status: 404 });
    }

    // 转发到 Telegram API
    const tgUrl = new URL(url.pathname + url.search, `https://${TG_HOST}`);
    const headers = new Headers(request.headers);
    headers.delete("X-TCC-Key");
    headers.set("Host", TG_HOST);

    const response = await fetch(tgUrl.toString(), {
      method: request.method,
      headers,
      body: request.method !== "GET" ? request.body : undefined,
    });

    return new Response(response.body, {
      status: response.status,
      headers: response.headers,
    });
  },
};
