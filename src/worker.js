export default {
  async fetch(request, env) {
    const url = new URL(request.url);
    // One address only: https, no www.
    if (url.hostname === "www.froe.sh" || url.protocol === "http:") {
      return new Response(null, {
        status: 301,
        headers: {
          location: "https://froe.sh" + url.pathname + url.search,
          "cache-control": "public, max-age=3600",
        },
      });
    }
    return env.ASSETS.fetch(request);
  },
};
