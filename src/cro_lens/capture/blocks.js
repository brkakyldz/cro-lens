(prefix) => {
  const SEL = 'h1,h2,h3,h4,h5,h6,p,li,a,button,label,input,select,textarea,summary,figcaption,blockquote,td,th,dt,dd,span,strong,small';
  const CONTAINERS = new Set(['LI', 'TD', 'TH', 'DD', 'SPAN', 'STRONG', 'SMALL', 'LABEL', 'BLOCKQUOTE']);
  const PRICE = /([$€£¥₺]\s?\d)|(\d[\d.,]*\s?(USD|EUR|GBP|TRY))|(\/\s?(mo|month|yr|year|user)\b)|(per (month|year|user))/i;
  const visible = (el) => {
    const r = el.getBoundingClientRect();
    if (r.width < 2 || r.height < 2) return false;
    const cs = getComputedStyle(el);
    return !(cs.visibility === 'hidden' || cs.display === 'none' || +cs.opacity === 0);
  };
  const textOf = (el) => {
    let t = '';
    if (el.tagName === 'INPUT' || el.tagName === 'TEXTAREA' || el.tagName === 'SELECT') {
      const lab = el.labels && el.labels[0] ? el.labels[0].innerText : '';
      t = el.placeholder || el.getAttribute('aria-label') || lab || el.name || el.value || '';
      if ((el.type === 'submit' || el.type === 'button') && el.value) t = el.value;
    } else {
      t = el.innerText || el.getAttribute('aria-label') || '';
    }
    return t.trim().replace(/\s+/g, ' ');
  };
  const isCta = (el) => {
    if (el.tagName === 'BUTTON') return true;
    if (el.tagName === 'INPUT' && (el.type === 'submit' || el.type === 'button')) return true;
    if (el.tagName !== 'A') return false;
    if (el.getAttribute('role') === 'button') return true;
    if (/(^|[\s_-])(btn|button|cta)([\s_-]|$)/i.test(el.className || '')) return true;
    const cs = getComputedStyle(el);
    const bg = cs.backgroundColor;
    const filled = bg && bg !== 'transparent' && !/rgba\(.*,\s*0\)$/.test(bg);
    return filled && parseFloat(cs.paddingLeft) >= 8;
  };
  const cands = [...document.querySelectorAll(SEL)].filter(visible);
  const set = new Set(cands);
  const out = [];
  let n = 0;
  for (const el of cands) {
    const t = textOf(el);
    if (!t) continue;
    if (CONTAINERS.has(el.tagName)) {
      let inner = false;
      for (const d of el.querySelectorAll(SEL)) { if (set.has(d) && textOf(d)) { inner = true; break; } }
      if (inner && el.tagName !== 'LABEL') continue;
      if (el.tagName === 'SPAN' || el.tagName === 'STRONG' || el.tagName === 'SMALL') {
        const p = el.parentElement && el.parentElement.closest('h1,h2,h3,h4,h5,h6,p,li,a,button,label,td,th,dd,blockquote');
        if (p && set.has(p)) continue;
      }
    }
    const tag = el.tagName.toLowerCase();
    let role = 'text';
    if (/^h[1-6]$/.test(tag)) role = 'heading';
    else if (isCta(el)) role = 'cta';
    else if (tag === 'a') role = 'link';
    else if (tag === 'input' || tag === 'select' || tag === 'textarea') role = 'form_field';
    if (role === 'text' && t.length < 80 && PRICE.test(t)) role = 'price';
    const r = el.getBoundingClientRect();
    out.push({id: prefix + (++n), tag, role, text: t.slice(0, 400),
      bbox: [Math.round(r.x + scrollX), Math.round(r.y + scrollY), Math.round(r.width), Math.round(r.height)]});
  }
  return {blocks: out, height: document.documentElement.scrollHeight, title: document.title,
          bodyText: (document.body ? document.body.innerText : '').slice(0, 4000),
          hasPassword: !!document.querySelector('input[type=password]')};
}
