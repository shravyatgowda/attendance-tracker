let token = null;
let role = null;

async function login() {
  const username = document.getElementById('username').value;
  const password = document.getElementById('password').value;

  const res = await fetch('/api/login', {
    method: 'POST',
    headers: { 'Content-Type': 'application/json' },
    body: JSON.stringify({ username, password }),
  });
  const data = await res.json();

  if (!res.ok) {
    document.getElementById('login-error').textContent = data.error;
    return;
  }

  token = data.token;
  role = data.role;
  document.getElementById('login-section').style.display = 'none';
  document.getElementById('app-section').style.display = 'block';
  document.getElementById('welcome-name').textContent = data.full_name;
  document.getElementById('welcome-role').textContent = data.role;
  if (role === 'admin') {
    document.getElementById('admin-panel').style.display = 'block';
  }
  loadHistory();
}

function authHeaders() {
  return { Authorization: `Bearer ${token}` };
}

async function doCheckIn() {
  const res = await fetch('/api/checkin', { method: 'POST', headers: authHeaders() });
  const data = await res.json();
  const resultEl = document.getElementById('checkin-result');
  if (res.ok) {
    resultEl.textContent = `Checked in at ${data.check_in_time} (${data.status})`;
    resultEl.className = 'success';
    loadHistory();
  } else {
    resultEl.textContent = data.error;
    resultEl.className = 'error';
  }
}

async function loadHistory() {
  const res = await fetch('/api/history', { headers: authHeaders() });
  const data = await res.json();
  const tbody = document.querySelector('#history-table tbody');
  tbody.innerHTML = '';
  for (const record of data.history) {
    const tr = document.createElement('tr');
    tr.innerHTML = `<td>${record.attendance_date}</td><td>${record.check_in_time}</td><td>${record.status}</td>`;
    tbody.appendChild(tr);
  }
}

async function loadReport() {
  const date = document.getElementById('report-date').value;
  const res = await fetch(`/api/report?date=${date}`, { headers: authHeaders() });
  const data = await res.json();
  const summaryEl = document.getElementById('report-summary');
  if (!res.ok) {
    summaryEl.textContent = data.error;
    return;
  }
  summaryEl.innerHTML = `
    <p>Total: ${data.total_employees} | Present: ${data.present_count} | Late: ${data.late_count} | Absent: ${data.absent_count}</p>
  `;
}
