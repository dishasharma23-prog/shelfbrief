// Renders every section from data/site.json (written by `python -m shelfbrief run`), then layers motion on top:
// a load sequence, Lenis smooth scroll, GSAP ScrollTrigger chapters, a custom cursor and the curved product
// carousel whose bottles are rendered once by scene.js. Everything is readable without the motion layer:
// entrances are only built when their section reaches the viewport, so if GSAP never loads, a trigger never
// fires or the visitor prefers reduced motion, every section simply sits in its final state.
const $ = (s, el = document) => el.querySelector(s);
const $$ = (s, el = document) => [...el.querySelectorAll(s)];
const esc = s => String(s ?? "").replace(/[&<>"']/g, c => ({ "&": "&amp;", "<": "&lt;", ">": "&gt;", '"': "&quot;", "'": "&#39;" })[c]);
const inr = n => (n == null ? "—" : "₹" + Math.round(n).toLocaleString("en-IN"));
const int = n => (n == null ? "—" : Math.round(n).toLocaleString("en-IN"));
const cssVar = name => getComputedStyle(document.documentElement).getPropertyValue(name).trim();
const SERIES = ["--s1", "--s2", "--s3", "--s4", "--s5"];

const REDUCED = matchMedia("(prefers-reduced-motion: reduce)").matches;
const FINE = matchMedia("(hover: hover) and (pointer: fine)").matches;
const MOBILE = matchMedia("(max-width: 900px)").matches || !FINE;
const WIDE = () => matchMedia("(min-width: 1024px)").matches;

async function loadData() {
  if (window.SHELF_DATA) return window.SHELF_DATA;
  const r = await fetch("data/site.json", { cache: "no-store" });
  if (!r.ok) throw new Error(`data/site.json returned ${r.status}`);
  return r.json();
}

// Waits briefly for the deferred CDN scripts; the page still works if they never arrive.
function libs() {
  return new Promise(res => {
    const t0 = performance.now();
    (function poll() {
      if (window.gsap && window.ScrollTrigger) return res(true);
      if (performance.now() - t0 > 2500) return res(false);
      setTimeout(poll, 40);
    })();
  });
}

function render(data) {
  const { run, insights, products, briefs } = data;
  const brandList = [...new Set(products.map(p => p.brand_slug))].sort();
  const brandName = Object.fromEntries(products.map(p => [p.brand_slug, p.brand]));
  const slugOf = Object.fromEntries(products.map(p => [p.brand, p.brand_slug]));
  // Colour follows the brand (alphabetical slot), never its rank; brands past the 5th share a neutral.
  const colorVar = slug => { const i = brandList.indexOf(slug); return i >= 0 && i < SERIES.length ? SERIES[i] : "--other"; };
  const colorFor = slug => cssVar(colorVar(slug));
  const swatch = slug => `<span class="swatch" style="background:var(${colorVar(slug)})"></span>`;
  const per = p => (p.price_per_100 ? `${inr(p.price_per_100)} / 100 ${p.size_unit}` : "—");

  // ---------- hero badge ----------
  const when = new Date(run.generated_at);
  const stamp = when.toLocaleDateString("en-IN", { day: "numeric", month: "long", year: "numeric", timeZone: "Asia/Kolkata" });
  const nBrands = insights.totals?.brands ?? brandList.length;
  $("#badge-text").textContent = `${int(run.clean_products)} ${run.sample ? "sample" : "real"} products · ${nBrands} brand${nBrands === 1 ? "" : "s"} · robots.txt respected`;
  $(".badge").classList.toggle("sample", !!run.sample);
  $("#sample-note").hidden = !run.sample;
  $("#foot-run").textContent = `Data from the run on ${stamp}. Re-scraped every Monday by GitHub Actions.`;

  // ---------- 01 request log ----------
  const hostOf = slug => { const p = products.find(x => x.brand_slug === slug); try { return new URL(p.url).host.replace(/^www\./, ""); } catch { return slug; } };
  const L = (verb, text, end = "", cls = "") => `<li class="${cls}"><span class="verb">${verb}</span><span>${text}</span><span>${end}</span></li>`;
  const logLines = [];
  (insights.by_brand || []).slice().sort((a, b) => a.brand.localeCompare(b.brand)).forEach((b, i) => {
    const h = esc(hostOf(b.slug));
    if (i) logLines.push(L("wait", "next store", "", "wait"));
    logLines.push(L("GET", `${h}/robots.txt`, `<span class="ok">200</span>`));
    logLines.push(L("check", `/products.json allowed for ShelfBriefBot`, `<span class="ok">yes</span>`, "note"));
    logLines.push(L("wait", "1.5 s", "", "wait"));
    logLines.push(L("GET", `${h}/products.json?limit=250&amp;page=1`, `<span class="ok">200</span>`));
    if ((run.rate_limited || []).includes(b.brand))
      logLines.push(L("429", `product pages: store asked us to slow down, so we stopped`, `<span class="warn">backed off</span>`));
    logLines.push(L("keep", `${b.products} clean products from ${esc(b.brand)}, ${b.rated} rated`, "", "note"));
  });
  (run.sites_skipped || []).forEach(s => logLines.push(L("skip", `${esc(s.name)}: ${esc(s.reason)}`, `<span class="warn">skip</span>`)));
  logLines.push(L("done", `${int(run.requests)} requests, ${int(run.cache_hits)} from cache, ${int(run.retries)} retries`, "", "note"));
  logLines.push(L("brief", `${int(run.briefs)} campaign briefs written`, `<span class="ok">ok</span>`));
  $("#log").innerHTML = logLines.join("");

  $("#numerals").innerHTML = [
    [`${run.sites_ok}<small>of ${run.sites_checked}</small>`, "stores checked robots.txt before a single product page was read"],
    [`1.5<small>s</small>`, "minimum gap between two requests to the same store"],
    [int(run.requests), "requests in the whole last run, product pages included"],
    [int(run.pages_parsed), "product pages parsed for ratings, reviews and offers"],
  ].map(([n, t]) => `<div><dd>${n}</dd><dt>${t}</dt></div>`).join("");

  // ---------- 02 raw -> clean ----------
  renderTransform(data, { swatch, colorFor, per });

  // ---------- 03 insights ----------
  const charts = renderInsights(data, { brandList, brandName, colorVar, swatch, slugOf, per });

  // ---------- explorer ----------
  renderExplorer(products, { brandList, brandName, swatch });

  // ---------- 04 briefs ----------
  renderBriefs(briefs, { slugOf, colorVar });

  return { colorFor, charts, brandList };
}

// ===================================================================================================
// 02: one real catalog record next to the clean row
function renderTransform(data, { colorFor, per }) {
  const raw = data.raw_example;
  const p = (raw && data.products.find(x => x.url === raw.url)) || data.briefs[0]?.product || data.products[0];
  if (!p) return;
  const full = data.products.find(x => x.url === p.url) || p;

  // raw side: hand-rolled JSON printer so tokens can be marked with the clean field they feed
  const sizeRe = /\b\d+(\.\d+)?\s?(ml|g|gm|l|kg)\b/i;
  const claimTerms = [...new Set([...(full.strengths || []), ...(full.ingredients || []), ...(full.free_from || [])])].sort((a, b) => b.length - a.length);
  const markStr = (s, k) => `<mark data-k="${k}">${esc(s)}</mark>`;
  function markClaims(text) {
    let out = esc(text);
    const used = new Set();
    for (const term of claimTerms) {
      const word = term.replace(/^[\d.]+%\s*/, "").replace(/-Free$/, "").split(" ")[0];
      if (!word || word.length < 3 || used.has(word.toLowerCase())) continue;
      const re = new RegExp(`(?<![\\w-])(${word.replace(/[.*+?^${}()|[\]\\]/g, "\\$&")})`, "i");
      if (re.test(out)) { out = out.replace(re, `<mark data-k="claims">$1</mark>`); used.add(word.toLowerCase()); }
    }
    return out;
  }
  function htmlString(s) {
    // tags dimmed (they get struck through), text kept, claim words marked
    return s.split(/(<[^>]+>)/g).map(part => part.startsWith("<") ? `<span class="tag">${esc(part)}</span>` : markClaims(part)).join("");
  }
  const q = s => `<span class="q">"</span>${s}<span class="q">"</span>`;
  const key = k => `<span class="k">"${k}"</span>: `;
  let out = "";
  if (raw) {
    const titleHtml = sizeRe.test(raw.title || "") ? esc(raw.title).replace(sizeRe, m => markStr(m, "size")) : esc(raw.title);
    const lines = [
      "{",
      `  ${key("title")}${q(`<mark data-k="title">${titleHtml}</mark>`)},`,
      `  ${key("product_type")}${q(raw.product_type ? markStr(raw.product_type, "category") : "")},`,
      `  ${key("body_html")}${q(htmlString(raw.body_html || "") + (raw.body_html && raw.body_html.length >= 700 ? "…" : ""))},`,
      `  ${key("variants")}[`,
      ...raw.variants.map((v, i) => {
        const vt = sizeRe.test(v.title || "") ? esc(v.title).replace(sizeRe, m => markStr(m, "size")) : esc(v.title);
        return `    { ${key("title")}${q(vt)}, ${key("price")}${q(i === 0 ? markStr(v.price, "price") : esc(v.price))}, ${key("compare_at_price")}${v.compare_at_price ? q(i === 0 ? markStr(v.compare_at_price, "mrp") : esc(v.compare_at_price)) : "null"} }${i < raw.variants.length - 1 ? "," : ""}`;
      }),
      "  ]",
      "}",
    ];
    out = lines.join("\n");
    $("#raw-src").textContent = "GET " + raw.source.replace(/^https?:\/\/(www\.)?/, "") + "  (one product, trimmed)";
  } else {
    out = "This run has no raw catalog sample.\nRun `python -m shelfbrief run` to capture one.";
  }
  $("#raw").innerHTML = out;

  const card = $("#label-card");
  card.style.setProperty("--brand", colorFor(full.brand_slug));
  const claims = [...(full.strengths || []), ...(full.spf ? [`SPF ${full.spf}`] : []), ...(full.ingredients || []).filter(i => !(full.strengths || []).some(s => s.includes(i))), ...(full.free_from || [])];
  card.innerHTML = `
    <div class="lc-brand"><span>${esc(full.brand)}</span><span>${esc(full.in_stock === false ? "out of stock" : "in stock")}</span></div>
    <h3 data-k="title">${esc(full.title)}</h3>
    <p class="lc-cat" data-k="category">${esc(full.category)}</p>
    <dl class="lc-rows">
      <div class="lc-row big" data-k="price"><dt>Price</dt><dd>${inr(full.price_inr)}</dd></div>
      <div class="lc-row" data-k="mrp"><dt>MRP and discount</dt><dd>${full.discount_pct > 0 ? `<span class="was">${inr(full.mrp_inr)}</span>${Math.round(full.discount_pct)}% off` : `${inr(full.mrp_inr)}, no discount`}</dd></div>
      <div class="lc-row" data-k="size"><dt>Pack size</dt><dd>${full.size ? `${+full.size.toFixed(1)} ${full.size_unit}` : "—"}</dd></div>
      <div class="lc-row big" data-k="per"><dt>Price per 100 ${esc(full.size_unit || "ml")}</dt><dd>${full.price_per_100 ? inr(full.price_per_100) : "—"}</dd></div>
      <div class="lc-row" data-k="rating"><dt>Rating</dt><dd>${full.rating ? `${full.rating.toFixed(1)} from ${int(full.review_count)}` : "not on page"}</dd></div>
    </dl>
    <p class="lc-claims" data-k="claims"><b>Claims found on the page</b>${claims.length ? esc(claims.join(", ")) : "None found"}</p>`;

  $("#clean-steps").innerHTML = [
    ["Name and category", "Title kept, product type mapped onto one shared category list."],
    ["Price from one variant", "Price and MRP read from the same variant, so the discount is real."],
    ["Pack size, unit price", "Sizes normalised (1 L becomes 1000 ml), then price per 100 ml or g."],
    ["Claims, not markup", "HTML stripped; ingredients, strengths and free-from labels extracted."],
  ].map(([b, t]) => `<li><b>${b}</b>${t}</li>`).join("");
}

// ===================================================================================================
// 03: insights. Charts are drawn at the figure's real width so text stays true to size.
function renderInsights(data, { brandList, brandName, colorVar, swatch }) {
  const { insights, products } = data;

  // headline: the widest spread in price per 100 within one category
  const withPer = products.filter(p => p.price_per_100 > 0 && !["Kits & Combos", "Other"].includes(p.category));
  const groups = {};
  withPer.forEach(p => (groups[`${p.category}|${p.size_unit}`] ||= []).push(p));
  let best = null;
  for (const [k, list] of Object.entries(groups)) {
    if (list.length < 3) continue;
    const sorted = list.slice().sort((a, b) => a.price_per_100 - b.price_per_100);
    const lo = sorted[0], hi = sorted[sorted.length - 1], ratio = hi.price_per_100 / lo.price_per_100;
    if (!best || ratio > best.ratio) best = { k, lo, hi, ratio, n: list.length };
  }
  if (best) {
    const [cat, unit] = best.k.split("|");
    $("#headline-stat").innerHTML = `<div class="big" data-count="${best.ratio.toFixed(1)}"><span class="n">${best.ratio.toFixed(1)}</span><span class="x">×</span></div>
      <p>Per 100 ${esc(unit)}, the priciest ${esc(cat.toLowerCase())} on this shelf costs ${best.ratio.toFixed(1)} times the cheapest.
      <small>${esc(best.hi.brand)} ${esc(best.hi.title)} at ${inr(best.hi.price_per_100)} per 100 ${esc(unit)} against ${esc(best.lo.brand)} ${esc(best.lo.title)} at ${inr(best.lo.price_per_100)}, across ${best.n} products.</small></p>`;
  } else {
    $("#headline-stat").hidden = true;
  }

  function tooltip(fig) {
    let tip = fig.querySelector(".vtip");
    if (!tip) { tip = document.createElement("div"); tip.className = "vtip"; tip.hidden = true; fig.appendChild(tip); }
    return {
      show(html, evt) {
        tip.innerHTML = html; tip.hidden = false;
        const r = fig.getBoundingClientRect();
        let x = evt.clientX - r.left + 16, y = evt.clientY - r.top + 16;
        if (x + 280 > r.width) x = Math.max(0, evt.clientX - r.left - 286);
        tip.style.left = x + "px"; tip.style.top = y + "px";
      },
      hide() { tip.hidden = true; },
    };
  }
  const legend = slugs => `<ul class="legend">${slugs.map(s => `<li>${swatch(s)}${esc(brandName[s])}</li>`).join("")}</ul>`;
  const slugByName = Object.fromEntries(Object.entries(brandName).map(([s, n]) => [n, s]));

  // --- price per 100: every product a dot, per category row, log scale ---
  function drawPrice() {
    const fig = $("#fig-price");
    const rows = Object.entries(groups).map(([k, list]) => ({ k, list, median: median(list.map(p => p.price_per_100)) }))
      .sort((a, b) => b.list.length - a.list.length).slice(0, 8).sort((a, b) => b.median - a.median);
    fig.innerHTML = `<h3>Price per 100 ml or g, product by product</h3>
      <p class="note">Each dot is one product, placed by what 100 ml or g of it costs. The dark tick is the category median. Log scale, so equal steps are equal ratios.</p>${legend(brandList)}`;
    if (!rows.length) { fig.insertAdjacentHTML("beforeend", `<p class="note">No pack sizes found yet.</p>`); return; }
    const W = Math.max(320, fig.clientWidth), narrow = W < 600;
    const Lw = narrow ? 0 : Math.min(210, W * 0.26), R = 18, rowH = narrow ? 64 : 46, top = 8, H = top + rows.length * rowH + 30;
    const all = rows.flatMap(r => r.list.map(p => p.price_per_100));
    const lmin = Math.log10(Math.max(1, Math.min(...all) * 0.8)), lmax = Math.log10(Math.max(...all) * 1.2);
    const x = v => Lw + ((Math.log10(v) - lmin) / (lmax - lmin)) * (W - Lw - R);
    const ticks = [5, 10, 20, 50, 100, 200, 500, 1000, 2000, 5000, 10000, 20000].filter(v => Math.log10(v) >= lmin && Math.log10(v) <= lmax);
    const tickSvg = ticks.map(v => `<line class="grid" x1="${x(v)}" x2="${x(v)}" y1="${top}" y2="${H - 24}"/><text class="tick" x="${x(v)}" y="${H - 6}" text-anchor="middle">₹${v >= 1000 ? v / 1000 + "k" : v}</text>`).join("");
    let di = 0;
    const dots = [];
    const rowSvg = rows.map((r, i) => {
      const [cat, unit] = r.k.split("|");
      const y0 = top + i * rowH, cy = y0 + (narrow ? 42 : rowH / 2);
      const label = narrow ? `<text x="0" y="${y0 + 16}">${esc(cat)} <tspan class="tick">per 100 ${unit}</tspan></text>`
        : `<text x="${Lw - 14}" y="${cy + 4}" text-anchor="end">${esc(cat)} <tspan class="tick">/${unit}</tspan></text>`;
      const pts = r.list.slice().sort((a, b) => a.price_per_100 - b.price_per_100).map((p, j) => {
        const jitter = ((j * 37) % 5 - 2) * 3.2;
        dots.push(p);
        return `<circle class="dot" data-d="${di++}" cx="${x(p.price_per_100)}" cy="${cy + jitter}" r="6" fill="var(${colorVar(p.brand_slug)})" stroke="var(--porcelain)" stroke-width="2"/>`;
      }).join("");
      return `<g data-row="${i}">${label}<line class="grid" x1="${Lw}" x2="${W - R}" y1="${cy}" y2="${cy}" style="stroke:var(--line-strong)"/>
        <line class="median" x1="${x(r.median)}" x2="${x(r.median)}" y1="${cy - 14}" y2="${cy + 14}" stroke="var(--ink)" stroke-width="2.5" stroke-linecap="round"/>${pts}</g>`;
    }).join("");
    fig.insertAdjacentHTML("beforeend", `<svg viewBox="0 0 ${W} ${H}" role="img" aria-label="Dot plot of price per 100 ml or g for each product, by category">${tickSvg}${rowSvg}</svg>`);
    const t = tooltip(fig);
    fig.querySelectorAll("circle.dot").forEach(c => {
      const p = dots[+c.dataset.d];
      c.addEventListener("pointerenter", () => c.setAttribute("r", 8.5));
      c.addEventListener("pointermove", e => t.show(`<b>${esc(p.title)}</b><br>${esc(p.brand)}<br><span class="m">${inr(p.price_inr)} for ${+p.size.toFixed(1)} ${p.size_unit}, ${inr(p.price_per_100)} per 100 ${p.size_unit}</span>`, e));
      c.addEventListener("pointerleave", () => { c.setAttribute("r", 6); t.hide(); });
    });
  }

  // --- hero ingredients: stacked by brand ---
  function drawIngredients() {
    const fig = $("#fig-ingredients");
    const rows = (insights.top_ingredients || []).slice(0, 8);
    const used = brandList.filter(s => rows.some(r => r.brands[brandName[s]]));
    fig.innerHTML = `<h3>The hero ingredients brands lean on</h3><p class="note">Products whose page names the ingredient, split by brand.</p>${legend(used)}`;
    if (!rows.length) { fig.insertAdjacentHTML("beforeend", `<p class="note">No ingredient claims found yet.</p>`); return; }
    const W = Math.max(300, fig.clientWidth), Lw = Math.min(150, W * 0.36), R = 34, rowH = 34, top = 4, H = top + rows.length * rowH + 4;
    const max = Math.max(...rows.map(d => d.count));
    const sx = v => (v / max) * (W - Lw - R);
    const svgRows = rows.map((d, i) => {
      const y = top + i * rowH + 9, h = 16;
      let x0 = Lw;
      const segs = brandList.filter(s => d.brands[brandName[s]]).map((s, j, arr) => {
        const n = d.brands[brandName[s]], w = Math.max(2, sx(n) - (j < arr.length - 1 ? 2 : 0));
        const rx = j === arr.length - 1 ? 4 : 0;
        const seg = rx ? `<path d="M${x0},${y} h${w - 4} a4,4 0 0 1 4,4 v${h - 8} a4,4 0 0 1 -4,4 h${-(w - 4)} z" fill="var(${colorVar(s)})"/>`
          : `<rect x="${x0}" y="${y}" width="${w}" height="${h}" fill="var(${colorVar(s)})"/>`;
        x0 += sx(n);
        return seg;
      }).join("");
      return `<g data-i="${i}"><rect class="hit" x="0" y="${top + i * rowH}" width="${W}" height="${rowH}"/>
        <text x="${Lw - 12}" y="${y + 12}" text-anchor="end">${esc(d.name)}</text>
        <g class="bar">${segs}</g><text class="tick" x="${x0 + 8}" y="${y + 12}">${d.count}</text></g>`;
    }).join("");
    fig.insertAdjacentHTML("beforeend", `<svg viewBox="0 0 ${W} ${H}" role="img" aria-label="Bar chart of the most-claimed ingredients, split by brand">${svgRows}</svg>`);
    fig.dataset.left = Lw;
    const t = tooltip(fig);
    fig.querySelectorAll("g[data-i]").forEach(g => {
      const d = rows[+g.dataset.i];
      g.addEventListener("pointermove", e => t.show(`<b>${esc(d.name)}</b>, ${d.count} product${d.count > 1 ? "s" : ""}<br><span class="m">${Object.entries(d.brands).map(([b, n]) => `${esc(b)} ${n}`).join(", ")}</span>`, e));
      g.addEventListener("pointerleave", t.hide);
    });
  }

  // --- claims: benefits and free-from, as a ranked typographic list ---
  function drawClaims() {
    const fig = $("#fig-claims");
    const list = [...(insights.top_benefits || []).slice(0, 6).map(d => ({ ...d, kind: "benefit" })),
      ...(insights.top_free_from || []).slice(0, 4).map(d => ({ ...d, kind: "free-from" }))]
      .sort((a, b) => b.count - a.count).slice(0, 8);
    const max = Math.max(1, ...list.map(d => d.count));
    fig.innerHTML = `<h3>What the copy promises</h3><p class="note">Most common benefit and free-from claims, counted across all products.</p>
      <ol class="claims-list">${list.map(d => `<li><span class="c-name">${esc(d.name)}<span class="c-kind">${d.kind}</span></span><span class="c-n">${d.count}</span>
        <span class="c-bar"><span class="${d.kind === "free-from" ? "free" : ""}" style="width:${(d.count / max) * 100}%"></span></span></li>`).join("")}</ol>`;
  }

  // --- brand cards ---
  $("#brand-row").innerHTML = (insights.by_brand || []).slice().sort((a, b) => a.brand.localeCompare(b.brand)).map(b => `
    <article class="brand-card" style="--brand:var(${colorVar(b.slug)})">
      <h4>${esc(b.brand)}</h4><p class="bc-sub">${b.products} products, mostly ${esc(b.top_category.toLowerCase())}</p>
      <dl><div><dt>Median price</dt><dd>${inr(b.median_price)}</dd></div><div><dt>Average rating</dt><dd>${b.avg_rating ? b.avg_rating.toFixed(2) : "—"}</dd></div>
      <div><dt>On discount</dt><dd>${b.on_discount_pct}%</dd></div><div><dt>New in 90 days</dt><dd>${b.new_90d}</dd></div></dl>
    </article>`).join("");

  const draw = () => { drawPrice(); drawIngredients(); drawClaims(); };
  draw();
  let lastW = $("#fig-price").clientWidth;
  new ResizeObserver(() => { const w = $("#fig-price").clientWidth; if (Math.abs(w - lastW) > 8) { lastW = w; draw(); window.ScrollTrigger?.refresh(); } }).observe($("#insights"));
  return { redraw: draw };
}
const median = a => { const s = a.slice().sort((x, y) => x - y), m = s.length >> 1; return s.length % 2 ? s[m] : (s[m - 1] + s[m]) / 2; };

// ===================================================================================================
function renderExplorer(products, { brandList, brandName, swatch }) {
  const cats = Object.entries(products.reduce((a, p) => (a[p.category] = (a[p.category] || 0) + 1, a), {})).sort((a, b) => b[1] - a[1]);
  $("#f-brand").innerHTML = `<option value="">All brands</option>` + brandList.map(s => `<option value="${esc(s)}">${esc(brandName[s])}</option>`).join("");
  $("#f-cat").innerHTML = `<option value="">All categories</option>` + cats.map(([c, n]) => `<option value="${esc(c)}">${esc(c)} (${n})</option>`).join("");
  const cols = [
    { key: "title", label: "Product" }, { key: "brand", label: "Brand" },
    { key: "price_inr", label: "Price", r: true }, { key: "size", label: "Size", r: true },
    { key: "price_per_100", label: "₹ per 100", r: true }, { key: "price_position", label: "Position" },
    { key: "review_count", label: "Rating", r: true }, { key: "claims", label: "Claims", nosort: true },
  ];
  const state = { q: "", brand: "", cat: "", sort: "review_count", dir: -1, limit: 10 };
  function rows() {
    const q = state.q.toLowerCase();
    const list = products.filter(p =>
      (!state.brand || p.brand_slug === state.brand) && (!state.cat || p.category === state.cat) &&
      (!q || [p.title, p.brand, p.category, ...(p.ingredients || []), ...(p.benefits || []), ...(p.free_from || []), ...(p.strengths || [])].join(" ").toLowerCase().includes(q)));
    const k = state.sort;
    return list.sort((a, b) => {
      const x = a[k], y = b[k];
      if (x == null && y == null) return a.title.localeCompare(b.title);
      if (x == null) return 1;
      if (y == null) return -1;
      return (typeof x === "string" ? x.localeCompare(y) : x - y) * state.dir || a.title.localeCompare(b.title);
    });
  }
  function draw() {
    const list = rows(), shown = list.slice(0, state.limit);
    $("#count").textContent = `${list.length} of ${products.length} products`;
    const head = `<thead><tr>${cols.map(c => {
      const sorted = state.sort === c.key ? ` aria-sort="${state.dir > 0 ? "ascending" : "descending"}"` : "";
      const arrow = state.sort === c.key ? (state.dir > 0 ? " ↑" : " ↓") : "";
      return `<th class="${c.r ? "r" : ""}" scope="col">${c.nosort ? c.label : `<button data-sort="${c.key}"${sorted}>${c.label}${arrow}</button>`}</th>`;
    }).join("")}</tr></thead>`;
    const body = shown.map(p => {
      const claims = [...(p.strengths || []).map(s => `<span class="chip strong">${esc(s)}</span>`),
        ...(p.spf ? [`<span class="chip strong">SPF ${p.spf}</span>`] : []),
        ...(p.ingredients || []).filter(i => !(p.strengths || []).some(s => s.includes(i))).slice(0, 2).map(s => `<span class="chip">${esc(s)}</span>`),
        ...(p.free_from || []).slice(0, 1).map(s => `<span class="chip">${esc(s)}</span>`)].slice(0, 4).join("");
      return `<tr>
        <td><a class="title" href="${esc(p.url)}" target="_blank" rel="noopener">${esc(p.title)}</a><span class="sub">${esc(p.category)}</span></td>
        <td><span class="brand">${swatch(p.brand_slug)}${esc(p.brand)}</span></td>
        <td class="r">${inr(p.price_inr)}${p.discount_pct > 0 ? `<br><span class="strike">${inr(p.mrp_inr)}</span> <span class="off">−${Math.round(p.discount_pct)}%</span>` : ""}</td>
        <td class="r">${p.size ? `${+p.size.toFixed(1)} ${p.size_unit}` : `<span class="none">—</span>`}</td>
        <td class="r">${p.price_per_100 ? inr(p.price_per_100) : `<span class="none">—</span>`}</td>
        <td>${p.price_position && p.price_position !== "None" ? `<span class="pos ${esc(p.price_position)}">${esc(p.price_position)}</span>` : `<span class="none">—</span>`}</td>
        <td class="r">${p.rating ? `${p.rating.toFixed(1)}<span class="sub">${int(p.review_count)} reviews</span>` : `<span class="none">—</span>`}</td>
        <td><div class="chips">${claims || `<span class="none">—</span>`}</div></td></tr>`;
    }).join("");
    $("#shelf-table").innerHTML = head + `<tbody>${body || `<tr><td colspan="8" class="none">No products match. Clear the search or pick another brand.</td></tr>`}</tbody>`;
    $("#more-row").innerHTML = list.length > shown.length ? `<button class="btn ghost" id="more" type="button">Show all ${list.length}</button>` : "";
  }
  $("#shelf-table").addEventListener("click", e => {
    const b = e.target.closest("button[data-sort]");
    if (!b) return;
    const k = b.dataset.sort;
    state.dir = state.sort === k ? -state.dir : (["review_count", "price_inr", "price_per_100"].includes(k) ? -1 : 1);
    state.sort = k;
    draw();
    $(`#shelf-table button[data-sort="${k}"]`)?.focus();
  });
  $("#more-row").addEventListener("click", e => { if (e.target.id === "more") { state.limit = Infinity; draw(); window.ScrollTrigger?.refresh(); } });
  $("#q").addEventListener("input", e => { state.q = e.target.value; draw(); });
  $("#f-brand").addEventListener("change", e => { state.brand = e.target.value; draw(); });
  $("#f-cat").addEventListener("change", e => { state.cat = e.target.value; draw(); });
  draw();
}

// ===================================================================================================
function renderBriefs(briefs, { slugOf, colorVar }) {
  $("#briefs-count").textContent = `${briefs.length} briefs, ${new Set(briefs.map(b => b.product.brand)).size} brands`;
  const list = (title, items) => items?.length ? `<h4>${title}</h4><ul>${items.map(x => `<li>${esc(x)}</li>`).join("")}</ul>` : "";
  $("#brief-list").innerHTML = briefs.map((b, i) => {
    const p = b.product;
    return `<article class="brief" data-i="${i}" style="--brand:var(${colorVar(slugOf[p.brand])})">
      <div class="b-meta"><span>${esc(p.brand)}</span><span>${esc(p.category)}, ${inr(p.price_inr)}</span></div>
      <header><h3>${esc(p.title)}</h3><p class="one">${esc(b.one_liner)}</p></header>
      <div><h4>Opening hooks</h4><ol class="hooks">${b.hooks.map(h => `<li>${esc(h)}</li>`).join("")}</ol></div>
      <div><h4>Proof points from the product page</h4><div class="chips">${b.proof_points.length ? b.proof_points.map(x => `<span class="chip strong">${esc(x)}</span>`).join("") : `<span class="chip">No specific claims; keep it to first impressions</span>`}</div></div>
      <div><h4>Creators to brief</h4><div class="chips">${b.creator_niches.map(x => `<span class="chip">${esc(x)}</span>`).join("")}</div></div>
      <details><summary>Audience, formats and guardrails</summary>${list("Audience", b.audience)}${list("Formats", b.formats)}${list("Guardrails", b.guardrails)}</details>
      <footer><span class="by mono">${b.written_by === "gemini" ? "Gemini, checked against page claims" : "Written from rules"}</span>
        <span class="b-actions"><a class="btn ghost" href="${esc(p.url)}" target="_blank" rel="noopener" data-cursor="Open">Product</a><button class="btn solid copy" type="button" data-cursor="Copy">Copy brief</button></span></footer>
    </article>`;
  }).join("");
  function briefText(b) {
    const p = b.product;
    return [`CAMPAIGN BRIEF: ${p.brand}, ${p.title}`, p.url, "", b.one_liner, "",
      "Audience:", ...b.audience.map(a => `- ${a}`), "", "Creators to brief:", ...b.creator_niches.map(a => `- ${a}`), "",
      "Opening hooks:", ...b.hooks.map((h, i) => `${i + 1}. ${h}`), "", "Formats:", ...b.formats.map(a => `- ${a}`), "",
      "Proof points (from the product page):", ...b.proof_points.map(a => `- ${a}`), "", "Guardrails:", ...b.guardrails.map(a => `- ${a}`)].join("\n");
  }
  $("#brief-list").addEventListener("click", async e => {
    const btn = e.target.closest(".copy"); if (!btn) return;
    const text = briefText(briefs[+btn.closest(".brief").dataset.i]);
    let ok = false;
    try { await navigator.clipboard.writeText(text); ok = true; }
    catch {
      const ta = document.createElement("textarea"); ta.value = text; ta.style.position = "fixed"; ta.style.opacity = "0";
      document.body.appendChild(ta); ta.select();
      try { ok = document.execCommand("copy"); } catch { ok = false; }
      ta.remove();
    }
    btn.textContent = ok ? "Copied" : "Copy failed";
    btn.classList.toggle("done", ok);
    setTimeout(() => { btn.textContent = "Copy brief"; btn.classList.remove("done"); }, 1800);
  });
}

// ===================================================================================================
// hero carousel: real products on cards that sit on the inside of a cylinder. Centre cards stand upright,
// cards toward the edges come closer, so they grow taller and lean out, the outer edge taller than the inner.
// It drifts right to left in a seamless loop, can be dragged or flung, then eases back to the slow drift.
function carouselItems(data, n) {
  const { products, briefs } = data;
  const briefed = new Set(briefs.map(b => b.product.url));
  const byBrand = {};
  products.filter(p => p.price_per_100 > 0 && !["Kits & Combos", "Other"].includes(p.category))
    .sort((a, b) => (briefed.has(b.url) - briefed.has(a.url)) || (b.review_count || 0) - (a.review_count || 0))
    .forEach(p => (byBrand[p.brand_slug] ||= []).push(p));
  const brands = Object.keys(byBrand).sort();
  const out = [], cats = new Set();
  // round robin over brands, preferring a category we haven't shown yet
  for (let round = 0; out.length < n && round < 60; round++)
    for (const s of brands) {
      if (out.length >= n) break;
      const list = byBrand[s];
      const i = list.findIndex(p => !cats.has(p.category));
      const p = list.splice(i >= 0 ? i : 0, 1)[0];
      if (p) { out.push(p); cats.add(p.category); if (cats.size > 9) cats.clear(); }
    }
  return out;
}

function makeCarousel(items, colorFor) {
  const band = $("#carousel"), track = $("#carousel-track");
  if (!band || !items.length) return null;
  const nameOf = p => p.title.replace(new RegExp(`^${p.brand}\\s*`, "i"), "").replace(/\s*\|.*$/, "").trim();
  const cards = items.map(p => {
    const a = document.createElement("a");
    a.className = "card";
    a.href = p.url; a.target = "_blank"; a.rel = "noopener"; a.draggable = false;
    a.dataset.cursor = "Open";
    a.style.setProperty("--brand", colorFor(p.brand_slug));
    a.setAttribute("aria-label", `${p.brand} ${nameOf(p)}, ${inr(p.price_inr)}, ${inr(p.price_per_100)} per 100 ${p.size_unit}. Opens the product page.`);
    a.innerHTML = `<div class="c-lift"><div class="c-in">
      <div class="c-art"><img alt="" draggable="false"><span class="c-fallback">${esc(nameOf(p).split(" ").slice(0, 3).join(" "))}</span></div>
      <div class="c-meta"><div class="c-brand"><i></i>${esc(p.brand)}</div><div class="c-name">${esc(nameOf(p))}</div>
      <div class="c-price"><span>${inr(p.price_inr)}</span><span class="c-per">${inr(p.price_per_100)} / 100 ${esc(p.size_unit)}</span></div></div>
    </div></div>`;
    track.appendChild(a);
    return a;
  });

  let W = 0, R = 1, spacing = 1, L = 1, auto = 0;
  function measure() {
    W = band.clientWidth;
    const small = W < 700;
    const ch = small ? Math.round(Math.min(210, Math.max(170, innerHeight * 0.22))) : Math.round(Math.min(300, Math.max(220, innerHeight * 0.3)));
    const cw = Math.round(ch * 0.74);
    spacing = cw + (small ? 14 : 26);
    L = spacing * cards.length;
    R = Math.max(W * (small ? 0.9 : 0.72), small ? 340 : 800);       // cylinder radius
    auto = REDUCED ? 0 : (small ? 20 : 30);                          // px per second of drift
    band.style.setProperty("--cw", cw + "px");
    band.style.setProperty("--ch", ch + "px");
    band.style.setProperty("--band-h", Math.round(ch * 1.12) + "px");     // edge cards may grow past the band; the hero only clips sideways
    track.style.perspective = Math.round(R * 1.06) + "px";   // perspective acts on the cards, the track's children
    // the "per 100 ml" note sits just above the band, its arrow reaching into the cards
    const note = $(".scribble-price");
    if (note) note.style.top = small ? "" : Math.round(band.offsetTop - note.offsetHeight + 34) + "px";
  }

  let offset = 0, vel = auto, seek = 0, dragging = false, hovering = false;
  function place() {
    for (let i = 0; i < cards.length; i++) {
      let a = (((i * spacing - offset) % L) + L) % L;
      if (a > L / 2) a -= L;
      const th = a / R, el = cards[i];
      if (Math.abs(th) > 1.25) { if (el.style.visibility !== "hidden") el.style.visibility = "hidden"; continue; }
      if (el.style.visibility) el.style.visibility = "";
      const x = R * Math.sin(th), z = R * (1 - Math.cos(th));
      el.style.transform = `translate3d(${x.toFixed(1)}px,0,${z.toFixed(1)}px) rotateY(${(-th).toFixed(4)}rad)`;
      el.style.zIndex = String(Math.round(z));
    }
  }

  let raf = 0, last = 0, onScreen = true;
  function tick(now) {
    raf = 0;
    const dt = Math.min(0.05, (now - (last || now)) / 1000);
    last = now;
    if (!dragging) {
      const target = hovering ? 0 : auto;
      // a fling decays slowly; the return to the drift is quicker
      const k = Math.abs(vel) > Math.abs(auto) * 1.5 + 10 ? 2.4 : 3.2;
      vel += (target - vel) * (1 - Math.exp(-dt * k));
      offset += vel * dt;
      if (seek) { const step = seek * (1 - Math.exp(-dt * 7)); offset += step; seek -= step; if (Math.abs(seek) < 0.5) { offset += seek; seek = 0; } }
    }
    place();
    if (running()) raf = requestAnimationFrame(tick);
  }
  const running = () => onScreen && !document.hidden && (dragging || seek || Math.abs(vel) > 0.3 || (!hovering && auto));
  // (re)starts the loop; the clock restarts too, so a pause never turns into one big jump
  function kick() {
    if (!raf && running()) { last = 0; raf = requestAnimationFrame(tick); }
  }

  // drag and fling. Pointer capture starts only after a few pixels, so a plain click still opens the card.
  let downX = 0, lastX = 0, lastT = 0, dragV = 0, pid = null, moved = false;
  band.addEventListener("pointerdown", e => {
    if (e.button !== 0) return;
    pid = e.pointerId; downX = lastX = e.clientX; lastT = e.timeStamp; dragV = 0; moved = false;
  });
  band.addEventListener("pointermove", e => {
    if (e.pointerId !== pid) return;
    if (!dragging) {
      if (Math.abs(e.clientX - downX) < 6) return;
      dragging = moved = true; seek = 0;
      band.setPointerCapture(pid); band.classList.add("dragging");
      kick();
    }
    const dx = e.clientX - lastX, dt = Math.max(8, e.timeStamp - lastT);
    offset -= dx;
    dragV = 0.7 * (-dx / dt * 1000) + 0.3 * dragV;
    lastX = e.clientX; lastT = e.timeStamp;
  });
  const end = e => {
    if (e.pointerId !== pid) return;
    pid = null;
    if (!dragging) return;
    dragging = false;
    band.classList.remove("dragging");
    vel = REDUCED ? 0 : Math.max(-1600, Math.min(1600, dragV));
    if (e.timeStamp - lastT > 90) vel = REDUCED ? 0 : auto;    // held still before letting go: no fling
    kick();
  };
  band.addEventListener("pointerup", end);
  band.addEventListener("pointercancel", end);
  band.addEventListener("click", e => { if (moved) { e.preventDefault(); e.stopPropagation(); moved = false; } }, true);
  band.addEventListener("dragstart", e => e.preventDefault());

  // hover lifts the card (CSS) and stops the drift so the card holds still under the pointer
  band.addEventListener("pointerover", e => { if (e.pointerType === "mouse" && e.target.closest(".card")) { hovering = true; } });
  band.addEventListener("pointerout", e => { if (e.pointerType === "mouse" && !e.relatedTarget?.closest?.(".card")) { hovering = false; kick(); } });
  // keyboard: a focused card glides to the centre
  band.addEventListener("focusin", e => {
    const i = cards.indexOf(e.target.closest(".card"));
    if (i < 0 || !e.target.matches(":focus-visible")) return;
    let a = (((i * spacing - offset) % L) + L) % L;
    if (a > L / 2) a -= L;
    seek = a; hovering = true; kick();
  });
  band.addEventListener("focusout", () => { hovering = false; kick(); });

  new IntersectionObserver(([en]) => { onScreen = en.isIntersecting; kick(); }).observe(band);
  document.addEventListener("visibilitychange", kick);
  new ResizeObserver(() => { measure(); place(); }).observe(band);
  measure();
  offset = -Math.round(spacing * 0.5);                  // start with a gap at the centre, not a card edge-on
  vel = auto;
  place();
  kick();

  return {
    cards,
    setImage(i, url) {
      const img = cards[i]?.querySelector("img");
      if (!img) return;
      img.onload = () => img.classList.add("ready");
      img.src = url;
    },
  };
}

// The bottles: scene.js renders each card's product once, offscreen, after the page is idle.
function renderBottles(items, colorFor, carousel) {
  const fail = () => document.documentElement.classList.add("no-3d");
  return new Promise(resolve => {
    const go = async () => {
      const small = innerWidth < 700;
      const size = small ? 240 : 320;
      const ok = await window.__renderBottles(items, colorFor, { width: size, height: size, onImage: (i, url) => carousel.setImage(i, url) });
      if (!ok) fail();
      resolve(ok);
    };
    if (window.__renderBottles) go();
    else {
      window.addEventListener("shelf3d-ready", go, { once: true });
      if (!window.SHELF_DATA) {                       // the single-file build inlines scene.js instead
        const s = document.createElement("script");
        s.type = "module"; s.src = "scene.js";
        s.onerror = () => { fail(); resolve(false); };
        document.body.appendChild(s);
      }
    }
  });
}

// ===================================================================================================
// cursor: a dot plus a lagging ring that grows over anything you can act on
function makeCursor() {
  if (!FINE || REDUCED) return null;
  document.documentElement.classList.add("has-cursor");
  const el = $(".cursor"), dot = $(".cursor-dot"), ring = $(".cursor-ring"), label = $(".cursor-label");
  el.classList.add("is-hidden");                      // until the mouse first moves
  let mx = -100, my = -100, rx = -100, ry = -100, raf = 0;
  const loop = () => {
    rx += (mx - rx) * 0.18; ry += (my - ry) * 0.18;
    dot.style.transform = `translate3d(${mx}px, ${my}px, 0)`;
    ring.style.transform = `translate3d(${rx}px, ${ry}px, 0)`;
    raf = Math.abs(mx - rx) + Math.abs(my - ry) > 0.2 ? requestAnimationFrame(loop) : 0;
  };
  addEventListener("pointermove", e => { if (e.pointerType !== "mouse") return; mx = e.clientX; my = e.clientY; el.classList.remove("is-hidden"); if (!raf) raf = requestAnimationFrame(loop); }, { passive: true });
  document.addEventListener("pointerleave", () => el.classList.add("is-hidden"));
  document.addEventListener("pointerover", e => {
    const t = e.target.closest("a, button, summary, select, input, label, [data-cursor]");
    const isText = t && (t.matches("input, select, label"));
    el.classList.toggle("is-link", !!t && !isText);
    el.classList.toggle("is-hidden", !!isText);
    label.textContent = t && !isText ? (t.dataset.cursor || (t.target === "_blank" ? "Open" : "")) : "";
    el.classList.toggle("on-night", !!e.target.closest(".ch-briefs .briefs-head, .ch-briefs .track-wrap, .log, .chapter-pill") && !e.target.closest(".brief"));
  });
  return {};
}

// ===================================================================================================
function motion(state) {
  const { gsap, ScrollTrigger } = window;
  gsap.registerPlugin(ScrollTrigger);
  const root = document.documentElement;

  // smooth scroll
  let lenis = null;
  if (window.Lenis && !REDUCED) {
    lenis = new window.Lenis({ lerp: 0.1, anchors: { offset: 0 }, autoRaf: false });
    lenis.on("scroll", ScrollTrigger.update);
    gsap.ticker.add(t => lenis.raf(t * 1000));
    gsap.ticker.lagSmoothing(0);
  }

  // top bar: hides on the way down, returns on the way up; switches ink over the dark chapter
  const bar = $(".topbar"), pill = $("#chapter-pill");
  ScrollTrigger.create({
    start: 0, end: "max",
    onUpdate: self => {
      bar.classList.toggle("scrolled", self.scroll() > 40);
      bar.classList.toggle("hide", self.direction > 0 && self.scroll() > innerHeight * 0.8);
    },
  });
  // Created after the pins (below), so their positions include the pin spacing.
  function wayfinding() {
    const night = on => { bar.classList.toggle("on-night", on); pill.classList.toggle("on-night", on); };
    ScrollTrigger.create({ trigger: ".ch-briefs", start: "top 60px", end: "bottom 60px", onToggle: s => night(s.isActive) });
    $$(".chapter").forEach(ch => ScrollTrigger.create({
      trigger: ch, start: "top 55%", end: "bottom 55%",
      onToggle: s => {
        if (!s.isActive) return;
        $(".cp-num", pill).textContent = ch.dataset.chapter;
        $(".cp-name", pill).textContent = ch.dataset.name;
        $$(".topnav a").forEach(a => a.classList.toggle("active", a.getAttribute("href") === "#" + ch.id));
      },
    }));
    ScrollTrigger.create({ trigger: "#polite", start: "top 80%", endTrigger: ".site", end: "top 80%", onToggle: s => pill.classList.toggle("show", s.isActive) });
    ScrollTrigger.sort();
    ScrollTrigger.refresh();
  }

  if (REDUCED) { wayfinding(); return { intro: () => Promise.resolve() }; }

  // An entrance is only built once its trigger reaches the viewport, so nothing is hidden ahead of time.
  const onEnter = (trigger, build, start = "top bottom-=40") => {
    if (trigger instanceof Element || $$(trigger).length) ScrollTrigger.create({ trigger, start, once: true, onEnter: build });
  };
  const settle = { clearProps: "transform,filter,opacity,visibility" };

  // chapter titles rise out of a blur, line by line; nothing clips the type
  $$(".ch-head h2").forEach(h => {
    h.innerHTML = h.innerHTML.split(/<br\s*\/?>/i).map(l => `<span class="line" style="display:block">${l}</span>`).join("");
    onEnter(h, () => gsap.from($$(".line", h), { y: 34, autoAlpha: 0, filter: "blur(12px)", duration: 1.1, ease: "power3.out", stagger: 0.1, ...settle }));
  });

  const mm = gsap.matchMedia();

  // 01: the request log writes itself in
  onEnter("#log", () => gsap.from($$("#log li"), { autoAlpha: 0, x: -10, duration: 0.45, ease: "power2.out", stagger: 0.07, ...settle }), "top 85%");

  // numerals count up once
  $$("#numerals dd").forEach(dd => {
    const node = [...dd.childNodes].find(n => n.nodeType === 3);
    if (!node) return;
    const target = parseFloat(node.textContent.replace(/,/g, ""));
    if (!isFinite(target)) return;
    const dec = /\./.test(node.textContent) ? 1 : 0, o = { v: 0 };
    gsap.to(o, { v: target, duration: 1.6, ease: "power3.out", scrollTrigger: { trigger: "#numerals", start: "top bottom-=40", once: true },
      onUpdate: () => { node.textContent = dec ? o.v.toFixed(1) : Math.round(o.v).toLocaleString("en-IN"); } });
  });

  // 02: raw tokens light up as the field they feed lands on the label
  const steps = [["title", "category"], ["price", "mrp"], ["size", "per"], ["claims", "rating"]];
  const rawEl = $(".raw"), stepEls = $$("#clean-steps li"), rowsK = $$("#label-card [data-k]");
  const marks = $$("#raw mark");
  // step -1: nothing yet; 0-3: that step's fields highlighted; 4: done, markup struck through
  let current = -2;
  const setStep = i => {
    if (i === current) return;
    current = i;
    const keys = i >= 0 && i < steps.length ? steps[i] : [];
    marks.forEach(m => m.classList.toggle("on", keys.includes(m.dataset.k)));
    rowsK.forEach(r => r.classList.toggle("hl", keys.includes(r.dataset.k)));
    stepEls.forEach((s, j) => s.classList.toggle("on", j <= i));
    rawEl.classList.toggle("strip", i >= 3);
  };
  // Every field on the label stays fully visible; the walk-through only highlights, field by field,
  // then ends with all four steps marked and the raw markup struck through.
  const cleanTl = () => {
    const tl = gsap.timeline();
    tl.from(".arrow span", { scaleX: 0, scaleY: 0, duration: 0.6, ease: "power2.inOut", clearProps: "transform" });
    steps.forEach((_, i) => tl.call(() => setStep(i), null, "+=0.5").to({}, { duration: 1 }));
    tl.call(() => setStep(steps.length));
    return tl;
  };
  setStep(steps.length);                              // the resting state, in case the walk-through never runs
  onEnter("#transform", () => { setStep(-1); cleanTl(); }, "top 70%");

  // 03: charts draw in once
  onEnter("#fig-price", () => $$("#fig-price g[data-row]").forEach((g, i) => {
    gsap.from($$("circle.dot", g), { scale: 0, transformOrigin: "50% 50%", duration: 0.7, ease: "back.out(2)", stagger: 0.03, delay: i * 0.06, clearProps: "transform" });
    gsap.from($$(".median", g), { scaleY: 0, transformOrigin: "50% 50%", duration: 0.5, delay: 0.3 + i * 0.06, clearProps: "transform" });
  }), "top 85%");
  const left = +($("#fig-ingredients")?.dataset.left || 0);
  onEnter("#fig-ingredients", () => gsap.from($$("#fig-ingredients .bar"), { scaleX: 0, svgOrigin: `${left} 0`, duration: 1.1, ease: "power3.out", stagger: 0.07 }), "top 85%");
  onEnter("#fig-claims", () => gsap.from($$("#fig-claims .c-bar span"), { scaleX: 0, duration: 1.1, ease: "power3.out", stagger: 0.07, clearProps: "transform" }), "top 85%");
  const big = $("#headline-stat .big");
  if (big) {
    const target = parseFloat(big.dataset.count), o = { v: 1 };
    const n = $(".n", big);
    gsap.to(o, { v: target, duration: 1.8, ease: "power3.out", scrollTrigger: { trigger: big, start: "top bottom-=40", once: true }, onUpdate: () => { n.textContent = o.v.toFixed(1); } });
  }

  // 04: briefs travel sideways while the chapter is pinned (wide screens)
  const track = $("#brief-list"), wrap = $("#track-wrap");
  mm.add("(min-width: 1024px)", () => {
    const dist = () => Math.max(0, track.scrollWidth - wrap.clientWidth);
    const tween = gsap.to(track, { x: () => -dist(), ease: "none",
      scrollTrigger: { trigger: ".briefs-pin", start: "top top", end: () => "+=" + dist(), pin: true, scrub: 0.8, invalidateOnRefresh: true } });
    // keyboard: bring a focused card into view by scrolling the page to its spot on the track
    const onFocus = e => {
      const card = e.target.closest(".brief"); if (!card) return;
      wrap.scrollLeft = 0;
      const st = tween.scrollTrigger, d = dist();
      const want = Math.min(d, Math.max(0, card.offsetLeft - 24));
      const y = st.start + (d ? (want / d) * (st.end - st.start) : 0);
      lenis ? lenis.scrollTo(y, { immediate: true }) : window.scrollTo(0, y);
    };
    track.addEventListener("focusin", onFocus);
    return () => { track.removeEventListener("focusin", onFocus); gsap.set(track, { clearProps: "x" }); };
  });
  onEnter(".track-wrap", () => gsap.from(".brief", { y: 40, autoAlpha: 0, duration: 0.9, ease: "power3.out", stagger: 0.08, ...settle }));

  // footer name
  onEnter(".credit-name", () => gsap.from(".credit-name", { yPercent: 30, autoAlpha: 0, duration: 1.2, ease: "power4.out", ...settle }));
  wayfinding();

  // the load sequence: wordmark out, curtain up, the headline rises out of a blur, the notes draw themselves
  function drawNotes() {
    const tl = gsap.timeline();
    $$(".scribble").forEach((note, i) => {
      const paths = $$("path", note);
      paths.forEach(path => { const len = path.getTotalLength(); gsap.set(path, { strokeDasharray: len, strokeDashoffset: len }); });
      tl.fromTo($(".scribble-text", note), { clipPath: "inset(-20% 100% -20% 0)" }, { clipPath: "inset(-20% 0% -20% 0)", duration: 0.9, ease: "power1.inOut", clearProps: "clipPath" }, i * 0.5)
        .to(paths, { strokeDashoffset: 0, duration: 0.55, ease: "power1.inOut", stagger: 0.4, onComplete: () => gsap.set(paths, { clearProps: "strokeDasharray,strokeDashoffset" }) }, i * 0.5 + 0.5);
    });
    return tl;
  }
  function intro() {
    return new Promise(res => {
      const tl = gsap.timeline();
      gsap.set($$(".scribble-text"), { clipPath: "inset(-20% 100% -20% 0)" });
      tl.to(".loader-mark span", { yPercent: -110, duration: 0.8, ease: "power4.in", stagger: 0.05 })
        .to("#loader", { clipPath: "inset(0 0 100% 0)", duration: 1, ease: "power4.inOut" }, "-=0.2")
        .from(".badge", { autoAlpha: 0, y: 12, duration: 0.8, ease: "power3.out", ...settle }, "-=0.55")
        .from(".hero h1 .line", { y: 48, autoAlpha: 0, filter: "blur(18px)", duration: 1.4, ease: "power3.out", stagger: 0.14, ...settle }, "<")
        .from(".lede, .cta-row > .btn", { autoAlpha: 0, y: 16, duration: 0.9, ease: "power3.out", stagger: 0.08, ...settle }, "-=0.95")
        .from(".card .c-lift", { y: 90, autoAlpha: 0, duration: 1.2, ease: "power3.out", stagger: 0.05, ...settle }, "-=0.9")
        .add(drawNotes(), "-=1.1");
      lenis?.stop();
      // the page is usable before the notes finish drawing
      tl.call(() => { root.classList.add("loaded"); $("#loader")?.remove(); lenis?.start(); res(); }, null, "-=1.4");
    });
  }
  return { intro, lenis };
}

// ===================================================================================================
(async function main() {
  const root = document.documentElement;
  const loader = $("#loader");
  const bar = $("#loader-bar"), count = $("#loader-count"), msg = $("#loader-msg");
  const t0 = performance.now();
  let shown = 0;
  const progress = to => new Promise(res => {
    const from = shown, start = performance.now(), dur = 520;
    (function step(now) {
      const k = Math.min(1, (now - start) / dur), e = 1 - Math.pow(1 - k, 3);
      shown = from + (to - from) * e;
      if (bar) bar.style.transform = `scaleX(${shown / 100})`;
      if (count) count.textContent = Math.round(shown);
      k < 1 ? requestAnimationFrame(step) : res();
    })(performance.now());
  });

  let data;
  try {
    const p = progress(35);
    data = await loadData();
    await p;
  } catch (err) {
    loader?.remove();
    $("#badge-text").textContent = `Couldn't load the data file: ${err.message}. Run python -m shelfbrief run, then serve the web folder.`;
    return;
  }
  if (msg) msg.textContent = `${int(data.run.clean_products)} products, ${int(data.run.briefs)} briefs`;
  const state = render(data);
  const items = carouselItems(data, MOBILE ? 10 : 14);
  const carousel = makeCarousel(items, state.colorFor);
  // 3D bottles: rendered once, offscreen, while the loader is still up, so the cards rise in with them
  if (carousel) renderBottles(items, state.colorFor, carousel);
  const [hasLibs] = await Promise.all([libs(), document.fonts?.ready, progress(80)]);
  await progress(100);
  if (performance.now() - t0 < 900) await new Promise(r => setTimeout(r, 900 - (performance.now() - t0)));

  const cursor = makeCursor();
  let anim = null;
  if (hasLibs) {
    try { anim = motion(state); } catch (e) { console.error(e); }
  }
  if (anim && !REDUCED) await anim.intro();
  else { loader?.remove(); root.classList.add("loaded"); }

})();
