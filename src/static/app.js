function setResult(id, data) {
  const el = document.getElementById(id);
  el.textContent = JSON.stringify(data, null, 2);
}

async function postJSON(url, body) {
  const res = await fetch(url, {
    method: 'POST',
    headers: { 'Content-Type': 'application/json' },
    body: JSON.stringify(body || {})
  });
  const json = await res.json().catch(() => ({ error: 'Invalid JSON response' }));
  return { status: res.status, data: json };
}

document.getElementById('create-student-form').addEventListener('submit', async (e) => {
  e.preventDefault();
  const name = document.getElementById('student-name').value.trim();
  const r = await postJSON('/students', { name });
  setResult('create-student-result', r);
});

document.getElementById('get-student-form').addEventListener('submit', async (e) => {
  e.preventDefault();
  const id = document.getElementById('get-student-id').value;
  const res = await fetch(`/students/${id}`);
  const json = await res.json().catch(() => ({ error: 'Invalid JSON response' }));
  setResult('get-student-result', { status: res.status, data: json });
});

document.getElementById('recognition-form').addEventListener('submit', async (e) => {
  e.preventDefault();
  const sender_id = Number(document.getElementById('sender-id').value);
  const recipient_id = Number(document.getElementById('recipient-id').value);
  const amount = Number(document.getElementById('amount').value);
  const message = document.getElementById('message').value;
  const r = await postJSON('/recognitions', { sender_id, recipient_id, amount, message });
  setResult('recognition-result', r);
});

document.getElementById('endorsement-form').addEventListener('submit', async (e) => {
  e.preventDefault();
  const recognition_id = Number(document.getElementById('recognition-id').value);
  const endorser_id = Number(document.getElementById('endorser-id').value);
  const r = await postJSON('/endorsements', { recognition_id, endorser_id });
  setResult('endorsement-result', r);
});

document.getElementById('redemption-form').addEventListener('submit', async (e) => {
  e.preventDefault();
  const student_id = Number(document.getElementById('redeem-student-id').value);
  const amount = Number(document.getElementById('redeem-amount').value);
  const r = await postJSON('/redemptions', { student_id, amount });
  setResult('redemption-result', r);
});

document.getElementById('leaderboard-form').addEventListener('submit', async (e) => {
  e.preventDefault();
  const limitVal = document.getElementById('leaderboard-limit').value;
  const limit = limitVal ? Number(limitVal) : undefined;
  const url = limit ? `/leaderboard?limit=${limit}` : '/leaderboard';
  const res = await fetch(url);
  const json = await res.json().catch(() => ({ error: 'Invalid JSON response' }));
  setResult('leaderboard-result', { status: res.status, data: json });
});

