/**
 * BorrowHub - Data Studio
 * Database reporting dashboard, HTML-table output, aggregation / filter /
 * sub-query / join builders, controlled UPDATE form, report view + trigger
 * demonstration and XML output. Talks to the /api/explorer endpoints.
 */
(function () {
  "use strict";

  const TOKEN_KEY = "borrowhub_jwt_token";
  const USER_KEY = "borrowhub_user_profile";

  const el = (sel, root = document) => root.querySelector(sel);
  const esc = (v) =>
    String(v ?? "").replace(/[&<>"']/g, (c) => ({
      "&": "&amp;", "<": "&lt;", ">": "&gt;", '"': "&quot;", "'": "&#39;",
    }[c]));

  function token() {
    return localStorage.getItem(TOKEN_KEY) || "";
  }

  function currentUser() {
    try {
      return JSON.parse(localStorage.getItem(USER_KEY) || "null");
    } catch (e) {
      return null;
    }
  }

  function isAdmin() {
    const user = currentUser();
    return !!user && String(user.role || "").toUpperCase() === "ADMIN";
  }

  async function api(path, options = {}) {
    const headers = { ...(options.headers || {}) };
    if (token()) headers.Authorization = `Bearer ${token()}`;
    const res = await fetch(path, { ...options, headers });
    let body = null;
    try {
      body = await res.json();
    } catch (e) {
      body = null;
    }
    if (!res.ok) {
      const detail = body && body.detail ? body.detail : `HTTP ${res.status}`;
      throw new Error(typeof detail === "string" ? detail : JSON.stringify(detail));
    }
    return body;
  }

  function notice(message, isError = false) {
    const box = el("#studioNotice");
    if (!box) return;
    box.textContent = message;
    box.className = "studio-notice" + (isError ? " error" : " ok");
    box.hidden = false;
    clearTimeout(notice.timer);
    notice.timer = setTimeout(() => { box.hidden = true; }, 6000);
  }

  /* ------------------------------------------------------------------ */
  /* Rendering helpers                                                   */
  /* ------------------------------------------------------------------ */

  const isNumeric = (v) => typeof v === "number" || (typeof v === "string" && v !== "" && !Number.isNaN(Number(v)));

  function toCsv(columns, rows) {
    const quote = (v) => {
      if (v === null || v === undefined) return "";
      const text = String(v);
      return /[",\n]/.test(text) ? `"${text.replace(/"/g, '""')}"` : text;
    };
    return [columns.map(quote).join(",")]
      .concat(rows.map((r) => r.map(quote).join(",")))
      .join("\n");
  }

  function renderTable(payload, target, options = {}) {
    const host = typeof target === "string" ? el(target) : target;
    if (!host) return;
    if (!payload || !payload.rows || !payload.rows.length) {
      host.innerHTML = '<p class="studio-empty">No rows matched this query.</p>';
      return;
    }
    const numericCols = payload.columns.map((_, i) =>
      payload.rows.some((row) => typeof row[i] === "number"));
    const head = payload.columns
      .map((c, i) => `<th class="${numericCols[i] ? "num" : ""}">${esc(String(c).replace(/_/g, " "))}</th>`)
      .join("");
    const body = payload.rows
      .map((row) => `<tr>${row.map((v, i) => `<td class="${numericCols[i] ? "num" : ""}">${v === null ? '<span class="studio-null">NULL</span>' : esc(v)}</td>`).join("")}</tr>`)
      .join("");
    let html = `<div class="studio-table-wrap"><table class="studio-table"><thead><tr>${head}</tr></thead><tbody>${body}</tbody></table></div>`;
    const bits = [`${payload.row_count} row(s)`];
    if (payload.total !== undefined) bits.push(`${payload.total} in table`);
    if (payload.truncated) bits.push(`capped at ${payload.row_cap}`);
    html += `<p class="studio-meta">${bits.join(" &middot; ")}${payload.sql ? ` &middot; <code>${esc(payload.sql)}</code>` : ""}</p>`;
    if (options.xmlBox) {
      html += `<details class="studio-xml"><summary>View as XML</summary><pre id="${options.xmlBox}">${esc(payload.xml || "")}</pre></details>`;
    }
    if (options.csv !== false) {
      const csv = toCsv(payload.columns, payload.rows);
      html += `<button type="button" class="studio-export" data-csv="${esc(csv)}">⤓ Export CSV</button>`;
    }
    host.innerHTML = html;
  }

  function fillSelect(select, items, { valueKey = null, labelKey = null, placeholder = null } = {}) {
    if (!select) return;
    const opts = [];
    if (placeholder) opts.push(`<option value="">${esc(placeholder)}</option>`);
    items.forEach((item) => {
      if (typeof item === "string") {
        opts.push(`<option value="${esc(item)}">${esc(item)}</option>`);
      } else {
        const value = item[valueKey];
        const label = labelKey ? item[labelKey] : value;
        opts.push(`<option value="${esc(value)}">${esc(label)}</option>`);
      }
    });
    select.innerHTML = opts.join("");
  }


  /* ------------------------------------------------------------------ */
  /* Studio chrome: refresh, section jump links, CSV export              */
  /* ------------------------------------------------------------------ */

  function wireStudioChrome() {
    el("#studioRefresh")?.addEventListener("click", async (event) => {
      const btn = event.currentTarget;
      btn.disabled = true;
      btn.textContent = "Refreshing…";
      try {
        await start(true);
        notice("Every panel was re-read from the database.");
      } finally {
        btn.disabled = false;
        btn.textContent = "↻ Refresh all";
      }
    });

    document.querySelectorAll(".studio-jump [data-jump]").forEach((link) => {
      link.addEventListener("click", (event) => {
        event.preventDefault();
        const target = document.getElementById(link.dataset.jump);
        if (target) target.scrollIntoView({ behavior: "smooth", block: "start" });
      });
    });

    // One handler for every "Export CSV" button rendered anywhere in the studio.
    document.addEventListener("click", (event) => {
      const btn = event.target.closest("[data-csv]");
      if (!btn) return;
      const blob = new Blob([btn.dataset.csv], { type: "text/csv;charset=utf-8" });
      const url = URL.createObjectURL(blob);
      const a = document.createElement("a");
      a.href = url;
      a.download = "borrowhub-result.csv";
      a.click();
      URL.revokeObjectURL(url);
    });
  }

  /* ------------------------------------------------------------------ */
  /* 0. Query Lab - write and run read-only SQL from the browser         */
  /* ------------------------------------------------------------------ */

  const LAB_HISTORY_KEY = "borrowhub_query_lab_history";
  const labState = { examples: [], busy: false };

  function labHistory() {
    try {
      return JSON.parse(localStorage.getItem(LAB_HISTORY_KEY) || "[]");
    } catch (e) {
      return [];
    }
  }

  function pushLabHistory(sql) {
    if (!el("#qlHistoryOn")?.checked) return;
    const entries = labHistory().filter((item) => item !== sql);
    entries.unshift(sql);
    localStorage.setItem(LAB_HISTORY_KEY, JSON.stringify(entries.slice(0, 8)));
    renderLabHistory();
  }

  function renderLabHistory() {
    const box = el("#qlHistoryBox");
    const list = el("#qlHistoryList");
    if (!box || !list) return;
    const entries = labHistory();
    if (!entries.length) {
      box.hidden = true;
      return;
    }
    box.hidden = false;
    list.innerHTML = entries
      .map((sql, i) => `<li><button type="button" data-lab-history="${i}">${esc(sql.split("\n")[0].slice(0, 90))}</button></li>`)
      .join("");
    list.querySelectorAll("[data-lab-history]").forEach((btn) => {
      btn.addEventListener("click", () => {
        el("#qlSql").value = labHistory()[Number(btn.dataset.labHistory)] || "";
        el("#qlSql").focus();
      });
    });
  }

  function setLabStatus(html, kind) {
    const box = el("#qlStatus");
    if (!box) return;
    if (!html) {
      box.hidden = true;
      box.innerHTML = "";
      return;
    }
    box.hidden = false;
    box.className = "ql-status" + (kind ? " " + kind : "");
    box.innerHTML = html;
  }

  function setLabBusy(busy) {
    labState.busy = busy;
    const btn = el("#qlRun");
    if (btn) {
      btn.disabled = busy;
      btn.innerHTML = busy ? "Running…" : "Run query <kbd>⌘/Ctrl</kbd><kbd>↵</kbd>";
    }
  }

  function formatSql(sql) {
    const keywords = ["select", "from", "where", "inner join", "left join", "right join",
      "join", "group by", "order by", "having", "limit", "union all", "union", "on",
      "and", "or", "explain", "with", "as", "insert", "update", "delete"];
    let out = sql.replace(/\s+/g, " ").trim();
    keywords.forEach((kw) => {
      out = out.replace(new RegExp(`\\b${kw.replace(" ", "\\s+")}\\b`, "gi"),
        kw.toUpperCase());
    });
    ["FROM", "WHERE", "GROUP BY", "ORDER BY", "HAVING", "LIMIT", "INNER JOIN",
      "LEFT JOIN", "RIGHT JOIN", "JOIN", "UNION ALL", "UNION"].forEach((kw) => {
      out = out.replace(new RegExp(`\\s+${kw}\\s+`, "g"), `\n${kw} `);
    });
    out = out.replace(/\s*,\s*/g, ",\n       ");
    return out.replace(/\n{2,}/g, "\n").trim();
  }

  async function loadQueryExamples() {
    const select = el("#qlExample");
    if (!select) return;
    try {
      const data = await api("/api/query-lab/examples");
      labState.examples = data.groups || [];
      select.innerHTML =
        '<option value="">Choose a sample query…</option>' +
        labState.examples
          .map((group, gi) => `<optgroup label="${esc(group.group)}">` +
            group.items.map((item, ii) => `<option value="${gi}:${ii}">${esc(item.title)}</option>`).join("") +
            "</optgroup>")
          .join("");
    } catch (err) {
      select.innerHTML = '<option value="">Examples unavailable</option>';
    }
  }

  function renderLabPlan(data) {
    const box = el("#qlPlanBox");
    const host = el("#qlPlanResult");
    const note = el("#qlPlanNote");
    if (!box || !host) return;
    if (!data || !data.plan) {
      box.hidden = true;
      return;
    }
    box.hidden = false;
    if (note) {
      note.textContent = data.indexes_used && data.indexes_used.length
        ? `indexes: ${data.indexes_used.join(", ")}`
        : "no index used";
    }
    renderTable(
      { columns: data.plan.columns, rows: data.plan.rows, row_count: data.plan.row_count },
      host,
      { csv: false }
    );
  }

  async function runLabQuery() {
    if (labState.busy) return;
    const sql = (el("#qlSql")?.value || "").trim();
    if (!sql) {
      setLabStatus("Type a statement first — or pick one of the examples.", "error");
      el("#qlSql")?.focus();
      return;
    }
    setLabBusy(true);
    setLabStatus('<span class="ql-spinner"></span> Running against the live database…', "busy");
    try {
      const params = new URLSearchParams({
        sql,
        include_plan: el("#qlPlan")?.checked ? "true" : "false",
      });
      const data = await api(`/api/query-lab/run?${params.toString()}`, { method: "POST" });
      renderTable(data, "#qlResult");
      renderLabPlan(data);
      const ms = Number(data.execution_ms);
      setLabStatus(
        `<strong>${data.row_count} row(s)</strong> returned in <strong>${ms.toFixed(2)} ms</strong>` +
        (data.truncated ? ` — capped at ${data.row_cap} rows` : "") +
        ` · statement type ${esc(data.statement_type)}`,
        "ok"
      );
      pushLabHistory(sql);
      notice("Query executed successfully.");
    } catch (err) {
      el("#qlResult").innerHTML = "";
      renderLabPlan(null);
      setLabStatus(`<strong>Query failed</strong><br>${esc(err.message)}`, "error");
    } finally {
      setLabBusy(false);
    }
  }

  function initQueryLab() {
    const runBtn = el("#qlRun");
    if (!runBtn) return;

    el("#qlBadge").textContent = isAdmin()
      ? "signed in as administrator"
      : "administrator session required";
    el("#qlBadge").className = "ql-badge" + (isAdmin() ? "" : " warn");

    if (!isAdmin()) {
      // The endpoint refuses non-admin sessions; say so before they type.
      ["#qlRun", "#qlFormat", "#qlCopy"].forEach((sel) => {
        const node = el(sel);
        if (node) node.disabled = true;
      });
      setLabStatus(
        "The Query Lab runs arbitrary read-only SQL, so it is limited to the campus " +
        "administrator. Sign in with the <strong>Admin</strong> demo chip and reopen this page.",
        "error"
      );
    }

    loadQueryExamples();
    renderLabHistory();

    runBtn.addEventListener("click", runLabQuery);

    el("#qlExample")?.addEventListener("change", (event) => {
      const [gi, ii] = (event.target.value || "").split(":").map(Number);
      const group = labState.examples[gi];
      if (!group) return;
      el("#qlSql").value = group.items[ii].sql;
      el("#qlSql").focus();
    });

    el("#qlSql")?.addEventListener("keydown", (event) => {
      if ((event.ctrlKey || event.metaKey) && event.key === "Enter") {
        event.preventDefault();
        runLabQuery();
      }
    });

    el("#qlFormat")?.addEventListener("click", () => {
      const box = el("#qlSql");
      if (box && box.value.trim()) box.value = formatSql(box.value);
    });

    el("#qlCopy")?.addEventListener("click", async () => {
      const box = el("#qlSql");
      if (!box || !box.value.trim()) return;
      try {
        await navigator.clipboard.writeText(box.value);
        notice("SQL copied to the clipboard.");
      } catch (e) {
        box.select();
        document.execCommand("copy");
        notice("SQL copied to the clipboard.");
      }
    });

    el("#qlClear")?.addEventListener("click", () => {
      el("#qlSql").value = "";
      el("#qlResult").innerHTML = '<p class="studio-empty">Results appear here. Pick an example above to start.</p>';
      renderLabPlan(null);
      setLabStatus("");
      el("#qlSql").focus();
    });
  }

  /* ------------------------------------------------------------------ */
  /* 1. Dashboard                                                        */
  /* ------------------------------------------------------------------ */

  async function loadDashboard() {
    const cards = el("#studioSummary");
    const tableHost = el("#studioTableStats");
    try {
      const data = await api("/api/explorer/dashboard");
      const s = data.summary || {};
      const cardsData = [
        ["Students", s.students, "registered student accounts"],
        ["Active items", s.items_active, "listings open for borrowing"],
        ["Loans in progress", s.loans_in_progress, "scheduled, active or overdue"],
        ["Completed loans", s.loans_completed, "returned and settled"],
        ["Pending requests", s.pending_requests, "waiting for an owner decision"],
        ["Open disputes", s.open_disputes, "awaiting mediation"],
        ["Rental revenue", `Rs.${s.revenue_collected}`, "collected rental & late fees"],
        ["Deposits held", `Rs.${s.deposits_held}`, "security deposits in custody"],
        ["Average rating", s.average_rating ?? "-", "across all peer reviews"],
      ];
      if (cards) {
        cards.innerHTML = cardsData
          .map(([label, value, hint]) => `
            <div class="studio-kpi">
              <span class="studio-kpi-value">${esc(value ?? 0)}</span>
              <span class="studio-kpi-label">${esc(label)}</span>
              <span class="studio-kpi-hint">${esc(hint)}</span>
            </div>`)
          .join("");
      }
      const msg = el("#studioMessage");
      if (msg) msg.textContent = data.message || "";

      if (tableHost) {
        const max = Math.max(1, ...data.tables.map((t) => t.rows));
        tableHost.innerHTML = `
          <h3>Row count of every table</h3>
          <div class="studio-table-wrap">
            <table class="studio-table">
              <thead><tr><th>Table</th><th>Rows</th><th>Share</th></tr></thead>
              <tbody>
                ${data.tables.map((t) => `
                  <tr>
                    <td><code>${esc(t.table)}</code></td>
                    <td>${t.rows}</td>
                    <td><span class="studio-bar" style="width:${Math.round((t.rows / max) * 100)}%"></span></td>
                  </tr>`).join("")}
              </tbody>
            </table>
          </div>`;
      }
    } catch (err) {
      notice(`Dashboard could not be loaded: ${err.message}`, true);
    }
  }

  /* ------------------------------------------------------------------ */
  /* 2. Table browser  (HTML table + XML)                                */
  /* ------------------------------------------------------------------ */

  async function loadTable() {
    const table = el("#studioTableSelect").value;
    const limit = el("#studioRowLimit").value || 25;
    if (!table) return;
    try {
      const data = await api(`/api/explorer/table/${table}?limit=${encodeURIComponent(limit)}&fmt=xml`);
      renderTable(data, "#studioTableResult", { xmlBox: "studioTableXml" });
    } catch (err) {
      notice(`Could not read ${table}: ${err.message}`, true);
    }
  }

  /* ------------------------------------------------------------------ */
  /* 3. Aggregation (function + column + optional group by)              */
  /* ------------------------------------------------------------------ */

  function refreshAggregateColumns() {
    const table = el("#aggTable").value;
    const allColumns = window.__studioOptions.table_columns[table] || [];
    const numeric = window.__studioOptions.aggregatable[table] || [];
    fillSelect(el("#aggColumn"), allColumns, { placeholder: "choose column" });
    // SUM/AVG/MIN/MAX only accept numeric columns, so pre-select one of them.
    if (numeric.length) el("#aggColumn").value = numeric[0];
    fillSelect(el("#aggGroupBy"), allColumns, { placeholder: "(no grouping)" });
  }

  async function runAggregate() {
    const table = el("#aggTable").value;
    const column = el("#aggColumn").value;
    const fn = el("#aggFunction").value;
    const groupBy = el("#aggGroupBy").value;
    if (!table || !column) {
      notice("Pick a table and a column first.", true);
      return;
    }
    const params = new URLSearchParams({ table, column, function: fn, fmt: "xml" });
    if (groupBy) params.set("group_by", groupBy);
    try {
      const data = await api(`/api/explorer/aggregate?${params.toString()}`);
      renderTable(data, "#studioAggResult", { xmlBox: "studioAggXml" });
    } catch (err) {
      notice(`Aggregation failed: ${err.message}`, true);
    }
  }

  /* ------------------------------------------------------------------ */
  /* 4. Conditional filter (field + operator + value)                    */
  /* ------------------------------------------------------------------ */

  function refreshFilterFields() {
    const table = el("#filterTable").value;
    const fields = window.__studioOptions.filter_fields[table] || {};
    fillSelect(el("#filterField"), Object.keys(fields), { placeholder: "choose column" });
  }

  async function runFilter() {
    const table = el("#filterTable").value;
    const field = el("#filterField").value;
    const operator = el("#filterOperator").value;
    const value = el("#filterValue").value;
    if (!table || !field || value === "") {
      notice("Choose a table, a column and a value.", true);
      return;
    }
    const params = new URLSearchParams({ table, field, operator, value, fmt: "xml" });
    try {
      const data = await api(`/api/explorer/filter?${params.toString()}`);
      renderTable(data, "#studioFilterResult", { xmlBox: "studioFilterXml" });
    } catch (err) {
      notice(`Filter failed: ${err.message}`, true);
    }
  }

  /* ------------------------------------------------------------------ */
  /* 5. Multi-table query (sub-query / correlated sub-query)             */
  /* ------------------------------------------------------------------ */

  async function runMultiTable() {
    const mode = el("#multiMode").value;
    const params = new URLSearchParams({ mode, fmt: "xml" });
    if (mode === "subquery") {
      const hostel = el("#multiHostel").value;
      if (!hostel) {
        notice("Pick a hostel for the sub-query option.", true);
        return;
      }
      params.set("hostel", hostel);
    } else {
      params.set("min_deposit", el("#multiDeposit").value || "100");
    }
    try {
      const data = await api(`/api/explorer/multi-table?${params.toString()}`);
      const desc = el("#studioMultiDescription");
      if (desc) desc.textContent = data.description || "";
      renderTable(data, "#studioMultiResult", { xmlBox: "studioMultiXml" });
    } catch (err) {
      notice(`Multi-table query failed: ${err.message}`, true);
    }
  }

  function refreshMultiMode() {
    const mode = el("#multiMode").value;
    el("#multiHostelField").hidden = mode !== "subquery";
    el("#multiDepositField").hidden = mode !== "correlated";
  }

  /* ------------------------------------------------------------------ */
  /* 6. Join builder (two tables + join type)                            */
  /* ------------------------------------------------------------------ */

  async function runJoin() {
    const left = el("#joinLeft").value;
    const right = el("#joinRight").value;
    const joinType = el("#joinType").value;
    if (!left || !right) {
      notice("Pick both tables.", true);
      return;
    }
    const params = new URLSearchParams({ left, right, join_type: joinType, fmt: "xml" });
    try {
      const data = await api(`/api/explorer/join?${params.toString()}`);
      const info = el("#studioJoinInfo");
      if (info) info.textContent = `${data.join_type} on ${data.on}`;
      renderTable(data, "#studioJoinResult", { xmlBox: "studioJoinXml" });
    } catch (err) {
      notice(`Join failed: ${err.message}`, true);
    }
  }

  /* ------------------------------------------------------------------ */
  /* 7. Controlled update form (admin)                                   */
  /* ------------------------------------------------------------------ */

  async function loadUpdateOptions() {
    const user = currentUser();
    const gate = el("#studioUpdateGate");
    const form = el("#studioUpdateForm");
    if (!user || !["ADMIN", "MODERATOR"].includes(user.role)) {
      if (gate) gate.hidden = false;
      if (form) form.hidden = true;
      return;
    }
    if (gate) gate.hidden = true;
    if (form) form.hidden = false;
    try {
      const data = await api("/api/explorer/update-options");
      fillSelect(el("#updateTable"), data.tables.map((t) => t.table), { placeholder: "choose table" });
      window.__studioUpdateTables = data.tables;
    } catch (err) {
      notice(`Update options unavailable: ${err.message}`, true);
    }
  }

  function refreshUpdateColumns() {
    const table = el("#updateTable").value;
    const config = (window.__studioUpdateTables || []).find((t) => t.table === table);
    const columnSelect = el("#updateColumn");
    if (!config) {
      columnSelect.innerHTML = '<option value="">choose column</option>';
      return;
    }
    fillSelect(columnSelect, config.columns.map((c) => ({ value: c.name, label: `${c.name} (${c.kind})` })),
      { valueKey: "value", labelKey: "label", placeholder: "choose column" });
    refreshUpdateValueField();
  }

  function refreshUpdateValueField() {
    const table = el("#updateTable").value;
    const config = (window.__studioUpdateTables || []).find((t) => t.table === table);
    const columnName = el("#updateColumn").value;
    const valueHost = el("#updateValueHost");
    const column = config && config.columns.find((c) => c.name === columnName);
    const pkLabel = el("#updatePkLabel");
    if (pkLabel) pkLabel.textContent = config ? config.primary_key : "row id";
    if (!column) {
      valueHost.innerHTML = '<input id="updateValue" placeholder="new value" disabled>';
      return;
    }
    if (column.options && column.options.length) {
      valueHost.innerHTML = `<select id="updateValue">${column.options.map((o) => `<option value="${esc(o)}">${esc(o)}</option>`).join("")}</select>`;
    } else {
      valueHost.innerHTML = `<input id="updateValue" placeholder="new value" value="">`;
    }
  }

  async function submitUpdate(event) {
    event.preventDefault();
    const table = el("#updateTable").value;
    const rowId = el("#updateRowId").value;
    const column = el("#updateColumn").value;
    const value = el("#updateValue").value;
    if (!table || !rowId || !column) {
      notice("Table, row id and column are all required.", true);
      return;
    }
    const params = new URLSearchParams({ table, row_id: rowId, column, value });
    try {
      const data = await api(`/api/explorer/update?${params.toString()}`, { method: "PUT" });
      renderTable(data, "#studioUpdateResult");
      notice(data.message || "Row updated.");
      loadDashboard();
    } catch (err) {
      notice(`Update rejected: ${err.message}`, true);
    }
  }

  /* ------------------------------------------------------------------ */
  /* 8. Report view: read, insert through procedure, trigger impact      */
  /* ------------------------------------------------------------------ */

  async function loadView() {
    const view = el("#viewSelect").value;
    if (!view) return;
    try {
      const data = await api(`/api/explorer/view/${view}?fmt=xml`);
      renderTable(data, "#studioViewResult", { xmlBox: "studioViewXml" });
    } catch (err) {
      notice(`View could not be read: ${err.message}`, true);
    }
  }

  async function insertThroughView() {
    const view = el("#viewSelect").value;
    const payload = new URLSearchParams({
      owner_id: el("#viewOwner").value,
      category_id: el("#viewCategory").value,
      location_id: el("#viewLocation").value,
      title: el("#viewTitle").value,
      daily_fee: el("#viewFee").value,
      deposit_amount: el("#viewDeposit").value,
    });
    try {
      const data = await api(`/api/explorer/view/${view}/insert?${payload.toString()}`, { method: "POST" });
      renderTable(data, "#studioViewResult");
      notice(data.message || "Inserted through the stored procedure.");
      loadDashboard();
    } catch (err) {
      notice(`Procedure call failed: ${err.message}`, true);
    }
  }

  async function runViewTriggerDemo(event) {
    event.preventDefault();
    const view = el("#viewSelect").value;
    const params = new URLSearchParams({
      item_id: el("#triggerItemId").value,
      new_fee: el("#triggerFee").value,
      set_condition: el("#triggerCondition").value,
      set_status: el("#triggerStatus").value,
    });
    try {
      const data = await api(`/api/explorer/view/${view}/trigger-demo?${params.toString()}`, { method: "POST" });
      const host = el("#studioTriggerResult");
      const ok = data.outcome === "accepted";
      host.innerHTML = `
        <div class="studio-callout ${ok ? "ok" : "error"}">
          <strong>${ok ? "Change accepted" : "Change rejected by trigger"}</strong>
          <p>${esc(data.detail)}</p>
          <code>${esc(data.sql)}</code>
        </div>
        ${data.row_after && data.row_after.length ? `
          <h4>Row after the attempt</h4>
          <div class="studio-table-wrap"><table class="studio-table">
            <thead><tr>${Object.keys(data.row_after[0]).map((k) => `<th>${esc(k)}</th>`).join("")}</tr></thead>
            <tbody>${data.row_after.map((r) => `<tr>${Object.values(r).map((v) => `<td>${esc(v)}</td>`).join("")}</tr>`).join("")}</tbody>
          </table></div>` : ""}
        ${data.audit_tail && data.audit_tail.length ? `
          <h4>Latest audit-trail entries (application_audit_log)</h4>
          <div class="studio-table-wrap"><table class="studio-table">
            <thead><tr><th>log id</th><th>action</th><th>entity</th><th>old value</th><th>new value</th></tr></thead>
            <tbody>${data.audit_tail.map((a) => `<tr>
              <td>${esc(a.log_id)}</td><td>${esc(a.action)}</td><td>${esc(a.entity_id)}</td>
              <td><code>${esc(JSON.stringify(a.old_value))}</code></td>
              <td><code>${esc(JSON.stringify(a.new_value))}</code></td></tr>`).join("")}</tbody>
          </table></div>` : ""}`;
    } catch (err) {
      notice(`Trigger demonstration failed: ${err.message}`, true);
    }
  }

  /* ------------------------------------------------------------------ */
  /* Bootstrap                                                           */
  /* ------------------------------------------------------------------ */

  async function init() {
    if (!el("#dataStudio")) return;
    if (!token()) {
      // Nothing to report on until somebody signs in; the nav link triggers
      // a refresh once the session exists.
      notice("Sign in with a campus account to open the live database reports.", true);
      return;
    }

    try {
      const raw = await api("/api/explorer/options");
      const options = {
        tables: raw.tables || [],
        table_columns: raw.table_columns || {},
        aggregate_functions: raw.aggregate_functions || [],
        aggregatable: raw.aggregatable || {},
        filter_operators: raw.filter_operators || [],
        filter_fields: raw.filter_fields || {},
        join_types: raw.join_types || [],
        joins: raw.joins || [],
        hostels: raw.hostels || [],
        views: raw.views || [],
      };
      window.__studioOptions = options;
      fillSelect(el("#studioTableSelect"), options.tables, { placeholder: "choose table" });
      fillSelect(el("#aggTable"), Object.keys(options.aggregatable));
      fillSelect(el("#aggFunction"), options.aggregate_functions);
      fillSelect(el("#filterTable"), Object.keys(options.filter_fields));
      fillSelect(el("#filterOperator"), options.filter_operators);
      fillSelect(el("#joinLeft"), options.tables, { placeholder: "left table" });
      fillSelect(el("#joinRight"), options.tables, { placeholder: "right table" });
      fillSelect(el("#joinType"), options.join_types);
      fillSelect(el("#multiHostel"), options.hostels);
      if (options.hostels.length) el("#multiHostel").value = options.hostels[0];
      fillSelect(el("#viewSelect"), options.views);

      refreshAggregateColumns();
      refreshFilterFields();
      refreshMultiMode();
      loadDashboard();
      loadUpdateOptions();

      el("#studioTableSelect")?.addEventListener("change", loadTable);
      el("#studioRowLimit")?.addEventListener("change", loadTable);
      el("#aggRun")?.addEventListener("click", runAggregate);
      el("#aggTable")?.addEventListener("change", refreshAggregateColumns);
      el("#filterRun")?.addEventListener("click", runFilter);
      el("#filterTable")?.addEventListener("change", refreshFilterFields);
      el("#multiRun")?.addEventListener("click", runMultiTable);
      el("#multiMode")?.addEventListener("change", refreshMultiMode);
      el("#joinRun")?.addEventListener("click", runJoin);
      el("#updateTable")?.addEventListener("change", refreshUpdateColumns);
      el("#updateColumn")?.addEventListener("change", refreshUpdateValueField);
      el("#studioUpdateForm")?.addEventListener("submit", submitUpdate);
      el("#viewLoad")?.addEventListener("click", loadView);
      el("#viewSelect")?.addEventListener("change", loadView);
      el("#viewInsert")?.addEventListener("click", insertThroughView);
      el("#studioTriggerForm")?.addEventListener("submit", runViewTriggerDemo);
      el("#loginDataLoad")?.addEventListener("click", loadLoginData);
      initQueryLab();
      wireStudioChrome();
      el("#officeHoursToggle")?.addEventListener("click", toggleOfficeHours);
      loadOfficeHours();
    } catch (err) {
      notice(
        `Data Studio could not start (${err.message}). Sign in with a campus account and reopen this page.`,
        true
      );
    }
  }

  /* ------------------------------------------------------------------ */
  /* 9. Login record and the office-hours guard                          */
  /* ------------------------------------------------------------------ */

  function renderKeyValues(payload, target) {
    const host = el(target);
    if (!host) return;
    const rows = Object.entries(payload || {})
      .map(([k, v]) => `<tr><th>${esc(k)}</th><td>${esc(v === null ? "—" : v)}</td></tr>`)
      .join("");
    host.innerHTML = `<table class="studio-table"><tbody>${rows}</tbody></table>`;
  }

  async function loadLoginData() {
    try {
      const data = await api("/api/auth/login-data");
      renderKeyValues(data, "#studioLoginResult");
      notice("Login record read through sp_user_login_data.");
    } catch (err) {
      notice(`Login record could not be read: ${err.message}`, true);
    }
  }

  async function loadOfficeHours() {
    const state = el("#studioOfficeHoursState");
    try {
      const data = await api("/api/admin/office-hours");
      if (state) {
        state.textContent = data.enabled
          ? `Office-hours guard is ON — borrow-request changes are blocked outside ${data.allowed_day} ${data.allowed_window} (IST).`
          : `Office-hours guard is OFF — borrow-request changes are accepted at any time.`;
      }
      return data;
    } catch (err) {
      if (state) {
        state.textContent = isAdmin()
          ? `Office-hours state could not be read: ${err.message}`
          : "Sign in as the campus administrator to read or change the office-hours guard.";
      }
      return null;
    }
  }

  async function toggleOfficeHours() {
    const current = await loadOfficeHours();
    if (!current) {
      notice("Only the campus administrator can switch the office-hours guard.", true);
      return;
    }
    try {
      const data = await api(`/api/admin/office-hours?enabled=${current.enabled ? "false" : "true"}`, {
        method: "PUT",
      });
      notice(`Office-hours guard is now ${data.enabled ? "ON" : "OFF"} (sp_set_office_hours_guard).`);
      loadOfficeHours();
    } catch (err) {
      notice(`Office-hours guard could not be changed: ${err.message}`, true);
    }
  }

  // Re-runnable: the page is initialised on load, and again whenever the
  // Data Studio is opened after a sign-in (the endpoints need a JWT).
  let started = false;
  async function start(force) {
    if (started && !force) return;
    started = true;
    await init();
  }

  window.BorrowHubStudio = { refresh: () => start(true) };

  if (document.readyState === "loading") {
    document.addEventListener("DOMContentLoaded", () => start(false));
  } else {
    start(false);
  }
})();
