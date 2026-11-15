/*
 * demo-backend.js
 *
 * Outreach Desk was first built to run inside a host that provides a small document database
 * (window.host.use('db')). This file lets the same page run on its own: it implements the handful of
 * database calls the page uses (collection / doc / add / set / update / delete / onSnapshot / orderBy / limit)
 * on top of localStorage, and seeds it with FICTIONAL demo data on first load.
 *
 *   ?reset        restore the demo data
 *   ?today=YYYY-MM-DD   pretend today is that date (the demo data is generated relative to it)
 *
 * Nothing here is real: every company, person, number and date is invented for the demo.
 */
(function () {
  'use strict';
  if (window.host) return; // a real host runtime is present: do nothing

  var KEY = 'outreach-desk-demo-v1';
  var params = new URLSearchParams(location.search);
  if (params.get('today') && /^\d{4}-\d{2}-\d{2}$/.test(params.get('today'))) window.__today = params.get('today');

  /* ---------- tiny date helpers (local time) ---------- */
  function pad(n) { return String(n).padStart(2, '0'); }
  function iso(d) { return d.getFullYear() + '-' + pad(d.getMonth() + 1) + '-' + pad(d.getDate()); }
  function parse(s) { var p = s.split('-').map(Number); return new Date(p[0], p[1] - 1, p[2]); }
  function todayIso() { return window.__today || iso(new Date()); }
  function addDays(s, n) { var d = parse(s); d.setDate(d.getDate() + n); return iso(d); }
  function isBiz(s) { var w = parse(s).getDay(); return w !== 0 && w !== 6; }
  function bizBack(s, n) { var d = s; while (n > 0) { d = addDays(d, -1); if (isBiz(d)) n--; } return d; }
  function bizFwd(s, n) { var d = s; while (n > 0) { d = addDays(d, 1); if (isBiz(d)) n--; } return d; }
  function lastBiz(s) { var d = s; while (!isBiz(d)) d = addDays(d, -1); return d; }

  /* ---------- storage ---------- */
  var store = null;
  try { store = window.localStorage; store.setItem('__t', '1'); store.removeItem('__t'); } catch (e) { store = null; }
  var data = {}; // 'collection/id' -> document
  function persist() { if (store) { try { store.setItem(KEY, JSON.stringify(data)); } catch (e) {} } }
  function clone(o) { return o == null ? o : JSON.parse(JSON.stringify(o)); }

  /* ---------- listeners ---------- */
  var listeners = [];
  function collOf(path) { return path.split('/')[0]; }
  function notify(path) {
    listeners.slice().forEach(function (l) {
      if ((l.kind === 'doc' && l.path === path) || (l.kind === 'col' && l.name === collOf(path))) setTimeout(l.fire, 0);
    });
  }
  function colSnapshot(q) {
    var docs = Object.keys(data).filter(function (k) { return k.indexOf(q.name + '/') === 0 && k.split('/').length === 2; })
      .map(function (k) { return { id: k.split('/')[1], v: data[k] }; });
    if (q.order) docs.sort(function (a, b) {
      var x = a.v[q.order], y = b.v[q.order];
      return (x < y ? -1 : x > y ? 1 : 0) * (q.dir === 'desc' ? -1 : 1);
    });
    if (q.lim) docs = docs.slice(0, q.lim);
    return { docs: docs.map(function (d) { return { id: d.id, data: function () { return clone(d.v); } }; }) };
  }
  function query(name, order, dir, lim) {
    var q = { name: name, order: order, dir: dir, lim: lim };
    q.orderBy = function (f, d) { return query(name, f, d || 'asc', lim); };
    q.limit = function (n) { return query(name, order, dir, n); };
    q.add = function (doc) {
      var id = 'a' + Date.now().toString(36) + Math.random().toString(36).slice(2, 6);
      data[name + '/' + id] = clone(doc); persist(); notify(name + '/' + id);
      return Promise.resolve({ id: id });
    };
    q.onSnapshot = function (cb) {
      var l = { kind: 'col', name: name, fire: function () { cb(colSnapshot(q)); } };
      listeners.push(l); setTimeout(l.fire, 0);
      return function () { listeners.splice(listeners.indexOf(l), 1); };
    };
    return q;
  }
  function docRef(path) {
    return {
      set: function (o) { data[path] = clone(o); persist(); notify(path); return Promise.resolve(); },
      update: function (o) { data[path] = Object.assign({}, data[path] || {}, clone(o)); persist(); notify(path); return Promise.resolve(); },
      delete: function () { delete data[path]; persist(); notify(path); return Promise.resolve(); },
      onSnapshot: function (cb) {
        var l = { kind: 'doc', path: path, fire: function () { cb({ exists: path in data, id: path.split('/')[1], data: function () { return clone(data[path]); } }); } };
        listeners.push(l); setTimeout(l.fire, 0);
        return function () { listeners.splice(listeners.indexOf(l), 1); };
      }
    };
  }
  var DB = { collection: function (n) { return query(n); }, doc: docRef };
  var DL = {
    save: function (o) {
      var a = document.createElement('a');
      a.href = URL.createObjectURL(new Blob([o.data], { type: 'text/csv' }));
      a.download = o.filename; document.body.appendChild(a); a.click(); a.remove();
      return Promise.resolve();
    }
  };
  window.host = { use: function (n) { return n === 'db' ? Promise.resolve(DB) : n === 'downloads' ? Promise.resolve(DL) : Promise.reject(new Error('unsupported')); } };

  /* ---------- seed (fictional) ---------- */
  var seed = 7;
  function rnd() { seed = (seed * 1664525 + 1013904223) % 4294967296; return seed / 4294967296; }
  function pick(a) { return a[Math.floor(rnd() * a.length)]; }

  function makeSeed() {
    var T = lastBiz(todayIso());
    var d = {};
    var co = function (id, name, seg, tier, loc, size, members, context) {
      return { id: id, name: name, seg: seg, tier: tier, loc: loc, liSize: size, liMembers: String(members), otherSize: '', context: context, notes: '',
        web: 'https://example.com', liUrl: 'https://www.linkedin.com/company/example', genericEmail: 'info@example.com', source: 'Company website (fictional)', verified: bizBack(T, 6) };
    };
    var companies = [
      co('A-01', 'Northgate Mutual', 'A', 1, 'Springfield', '201-500 employees', 143, 'Regional insurer; operations team of about 40 handles claims by hand.'),
      co('A-02', 'Arbor Insurance Group', 'A', 1, 'Springfield', '51-200 employees', 77, 'Broker group that just merged two offices.'),
      co('A-03', 'Beacon Capital Partners', 'A', 2, 'Springfield', '51-200 employees', 52, 'Boutique asset manager; size not verified.'),
      co('A-04', 'Lumen Finance Co.', 'A', 1, 'Springfield', '201-500 employees', 188, 'Lender with a large HR and ops back office.'),
      co('C-01', 'Alder & Finch Retail', 'C', 1, 'Springfield', '201-500 employees', 121, 'Fashion retailer, 38 stores, one central buying team.'),
      co('C-02', 'Kestrel Home Stores', 'C', 2, 'Springfield', '51-200 employees', 64, 'Home goods chain; contacts still to map.'),
      co('C-03', 'Aurora Boutiques', 'C', 1, 'Springfield', '51-200 employees', 59, 'Family-owned boutique group, second generation now running it.'),
      co('C-04', 'Harbor Lane Outlet', 'C', 3, 'Elsewhere', '1001-5000 employees', 310, 'Probably too large for a first project.'),
      co('W-01', 'Warm network', 'W', 0, '', '', '', 'People who already know the work: alumni, past colleagues, introductions.')
    ];
    d['companies/all'] = { items: companies };

    var people = [
      // name, title, role, companyId, priority, origin, status, step, nextOffset (business days from today), nextAction
      ['Alex Morgan', 'Head of Operations', 'Ops', 'A-01', 1, 'Cold', 'Meeting', 1, 1, 'Put the meeting date in notes; prepare 3 discovery questions'],
      ['Priya Raman', 'Chief Operating Officer', 'COO', 'A-04', 1, 'Cold', 'Replied', 1, 0, 'Answer within 24 h'],
      ['Tomás Herrera', 'HR Director', 'HR', 'A-01', 1, 'Cold', 'Messaged', 1, 0, 'Follow-up 1 (a concrete use case)'],
      ['Mei Lin Zhou', 'Managing Director', 'MD', 'A-02', 1, 'Cold', 'Messaged', 2, -1, 'Follow-up 2 (a concrete use case)'],
      ['Daniel Okafor', 'Head of IT', 'IT', 'A-02', 2, 'Cold', 'Connect sent', 0, 0, 'Check if accepted; message them if yes'],
      ['Sofia Brandt', 'People & Culture Lead', 'HR', 'A-04', 2, 'Cold', 'Connected', 0, 0, 'Send first message (about their work, not a pitch)'],
      ['Liam Castellano', 'Operations Manager', 'Ops', 'A-03', 2, 'Cold', 'Target', 0, 0, 'Send LinkedIn connection request'],
      ['Hannah Weiss', 'Finance & Ops Director', 'Ops', 'A-03', 2, 'Cold', 'Target', 0, 1, 'Send LinkedIn connection request'],
      ['Rafael Duarte', 'COO', 'COO', 'A-04', 1, 'Cold', 'Emailed', 1, 2, 'Follow-up 1 (a concrete use case)'],
      ['Chloe Nakamura', 'Head of HR', 'HR', 'C-01', 1, 'Cold', 'Proposal', 1, 2, 'Proposal follow-up (day 3)'],
      ['Marco Bellini', 'Retail Operations Director', 'Ops', 'C-01', 1, 'Cold', 'Messaged', 1, 1, 'Follow-up 1 (a concrete use case)'],
      ['Ingrid Solheim', 'General Manager', 'MD', 'C-03', 1, 'Cold', 'Connected', 0, 0, 'Send first message (about their work, not a pitch)'],
      ['Omar Haddad', 'Head of IT', 'IT', 'C-03', 2, 'Cold', 'Connect sent', 0, 1, 'Check if accepted; message them if yes'],
      ['Lucía Ferreira', 'People Director', 'HR', 'C-02', 2, 'Cold', 'Target', 0, 0, 'Send LinkedIn connection request'],
      ['Ben Adler', 'Operations Lead', 'Ops', 'C-02', 3, 'Cold', 'Target', 0, 2, 'Send LinkedIn connection request'],
      ['Yara Costa', 'Chief of Staff', 'Other', 'C-04', 3, 'Cold', 'Nurture', 4, 40, 'Revisit: any news or a new use case?'],
      ['Victor Lindqvist', 'COO', 'COO', 'C-04', 3, 'Cold', 'Lost', 3, null, ''],
      ['Nadia Petrova', 'Operations Director', 'Ops', 'A-02', 2, 'Cold', 'Lost', 2, null, ''],
      ['Jordan Blake', 'Founder, Blake Advisory', 'Other', 'W-01', 1, 'Warm', 'Messaged', 1, 0, 'Follow-up 1 (a concrete use case)'],
      ['Camila Torres', 'Former colleague, now VP Ops', 'Ops', 'W-01', 1, 'Intro', 'Replied', 1, 0, 'Answer within 24 h'],
      ['Elias Novak', 'Alumni network, COO', 'COO', 'W-01', 2, 'Warm', 'Target', 0, 1, 'Send first message'],
      ['Grace Ibarra', 'Partner, regional law firm', 'MD', 'W-01', 2, 'Intro', 'Won', 3, null, '']
    ];
    var contacts = people.map(function (p, i) {
      var id = 'P-' + pad(i + 1) + '', c = companies.filter(function (x) { return x.id === p[3]; })[0];
      var closed = p[6] === 'Won' || p[6] === 'Lost';
      d['contacts/' + id] = {
        id: id, companyId: c.id, companyName: c.name, seg: c.seg, name: p[0], title: p[1], role: p[2], priority: p[4],
        li: 'https://www.linkedin.com/in/example', degree: i % 3 === 0 ? '2nd' : '', email: '', emailStatus: 'To find', origin: p[5], lang: 'EN',
        status: p[6], connectDate: null, msgDate: null, emailDate: null, lastTouch: bizBack(T, 1 + (i % 4)),
        nextAction: p[9], nextDate: p[8] === null ? null : (p[8] < 0 ? bizBack(T, -p[8]) : bizFwd(T, p[8])),
        replied: ['Replied', 'Meeting', 'Proposal', 'Won'].indexOf(p[6]) > -1 ? 'Yes' : '', notes: i === 0 ? 'Asked how we measure adoption after the workshop. Send the one-page method.' : '',
        outcome: p[6] === 'Lost' ? (p[0] === 'Victor Lindqvist' ? 'Already has a provider' : 'Not now / bad timing') : '', step: p[7], source: 'Demo data (fictional)', verified: bizBack(T, 5)
      };
      return d['contacts/' + id];
    });

    /* activity: the last 12 business days, derived from the contacts above */
    var seq = ['Connect request sent', 'Connection accepted', 'LinkedIn message sent', 'Follow-up sent', 'Email sent', 'Call made'];
    var days = [], dd = T; while (days.length < 12) { if (isBiz(dd)) days.unshift(dd); dd = addDays(dd, -1); }
    var ai = 0;
    days.forEach(function (day, di) {
      var n = di < 3 ? 3 + Math.floor(rnd() * 3) : 7 + Math.floor(rnd() * 7); // a slow start, then a steady rhythm
      if (day === T) n = 6;
      for (var k = 0; k < n; k++) {
        var c = pick(contacts), ev = pick(seq);
        var ts = parse(day).getTime() + (9 + Math.floor(rnd() * 8)) * 3600000 + Math.floor(rnd() * 3600000);
        d['activity/s' + (ai++)] = { date: day, contactId: c.id, contactName: c.name, company: c.companyName, seg: c.seg, event: ev, note: '', ts: ts };
      }
      if (di % 3 === 1) { // a reply or a meeting now and then
        var c2 = pick(contacts.filter(function (x) { return x.replied === 'Yes'; }));
        d['activity/s' + (ai++)] = { date: day, contactId: c2.id, contactName: c2.name, company: c2.companyName, seg: c2.seg, event: di % 2 ? 'Reply received' : 'Meeting booked', note: '', ts: parse(day).getTime() + 15 * 3600000 };
      }
      if (di === 7) { var c3 = contacts.filter(function (x) { return x.status === 'Lost'; })[0];
        d['activity/s' + (ai++)] = { date: day, contactId: c3.id, contactName: c3.name, company: c3.companyName, seg: c3.seg, event: '"No" received', note: c3.outcome, ts: parse(day).getTime() + 16 * 3600000 }; }
    });

    d['settings/targets'] = { daily: 10, floor: 4, connects: 7, meetingsWeek: 3, start: days[0], ltStart: days[0] };
    days.slice(0, -1).forEach(function (day, i) {
      d['daily/' + day] = { date: day, goalOutreach: 'Send ' + (i < 3 ? '6' : '10') + ' outreach',
        recapFirst: i % 2 ? 'Two follow-ups with a concrete use case got replies.' : 'Slow start; sent the connect requests first.',
        recapBlocker: i < 3 ? 'Writing the first message from scratch each time.' : '',
        hardThing: i < 3 ? 'Starting after a "No".' : '', liPosts: i % 3 === 0 ? 1 : 0, liComments: i % 4 };
    });

    /* LinkedIn analytics (fictional) */
    var ld = [], from = bizBack(T, 44), x = from, base = 40;
    while (x <= T) { if (isBiz(x)) { base = Math.max(12, base + (rnd() - 0.42) * 30); ld.push({ d: x, imp: Math.round(base * (rnd() > 0.88 ? 4 : 1)), eng: Math.round(base * 0.05), fol: rnd() > 0.7 ? 1 : 0 }); } x = addDays(x, 1); }
    var tot = ld.reduce(function (a, r) { return a + r.imp; }, 0);
    d['linkedin/summary'] = { from: from, to: T, impressions: tot, reached: Math.round(tot * 0.55), followers: 412, importedAt: T };
    d['linkedin/daily'] = { days: ld };
    var slugs = ['why-adoption-stalls-after-the-workshop', 'what-we-measured-after-six-weeks', 'a-checklist-before-you-buy-licences', 'three-habits-of-teams-that-keep-using-ai', 'what-managers-get-wrong-about-training', 'field-note-the-quiet-week-after-launch'];
    d['linkedin/posts'] = { items: slugs.map(function (s, i) {
      var imp = Math.round(120 + rnd() * 900);
      return { id: 'demo-post-' + i, url: 'https://www.linkedin.com/posts/demo_' + s + '-ugcPost-70000000000000000' + pad(i) + '-abcd', date: bizBack(T, 4 + i * 6), type: ['Text', 'Image', 'Text', 'Document', 'Text', 'Text'][i], imp: imp, outNet: Math.round(10 + rnd() * 40), eng: Math.round(imp * (0.02 + rnd() * 0.04)) };
    }) };
    d['signals/s1'] = { date: bizBack(T, 2), type: 'Inbound DM', who: 'Operations director, retailer', fit: 'Yes', note: 'Asked about a workshop for the buying team.', ts: Date.now() - 2 * 86400000 };
    d['signals/s2'] = { date: bizBack(T, 4), type: 'Connection request', who: 'HR manager', fit: 'Yes', note: '', ts: Date.now() - 4 * 86400000 };
    d['signals/s3'] = { date: bizBack(T, 5), type: 'Comment on my post', who: 'Consultant', fit: 'No', note: '', ts: Date.now() - 5 * 86400000 };
    return d;
  }

  function reset() { data = makeSeed(); persist(); }
  try { data = store ? JSON.parse(store.getItem(KEY) || 'null') || null : null; } catch (e) { data = null; }
  if (!data || params.has('reset')) { reset(); if (params.has('reset')) { params.delete('reset'); history.replaceState(null, '', location.pathname + (params.toString() ? '?' + params : '') + location.hash); } }

  /* ---------- a small banner so nobody mistakes this for real data ---------- */
  document.addEventListener('DOMContentLoaded', function () {
    var b = document.createElement('div');
    b.style.cssText = 'position:fixed;right:12px;bottom:12px;z-index:50;background:#142029;color:#fff;font:500 12px/1.4 system-ui,sans-serif;padding:8px 12px;border-radius:8px;display:flex;gap:10px;align-items:center;box-shadow:0 2px 8px rgba(0,0,0,.25)';
    b.innerHTML = '<span>Demo with fictional data. Stored only in this browser.</span><button type="button" style="all:unset;cursor:pointer;text-decoration:underline">Reset</button>';
    b.querySelector('button').onclick = function () { reset(); location.reload(); };
    document.body.appendChild(b);
  });
})();
