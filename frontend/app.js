const uploadForm = document.getElementById('upload-form');
const pdfInput = document.getElementById('pdf');
const uploadStatus = document.getElementById('upload-status');
const askButton = document.getElementById('ask-button');
const answer = document.getElementById('answer');
const modeSelect = document.getElementById('mode');
const questionInput = document.getElementById('question');

uploadForm.addEventListener('submit', async (event) => {
  event.preventDefault();
  const file = pdfInput.files[0];
  if (!file) {
    uploadStatus.textContent = 'Please choose a PDF file.';
    return;
  }

  uploadStatus.textContent = 'Uploading...';
  const formData = new FormData();
  formData.append('file', file);

  try {
    const response = await fetch('/api/upload_pdf', {
      method: 'POST',
      body: formData,
    });
    const data = await response.json();
    if (!response.ok) {
      uploadStatus.textContent = data.detail || 'Upload failed.';
      return;
    }
    uploadStatus.textContent = `Uploaded. ${data.chunks} chunks indexed.`;
  } catch (error) {
    uploadStatus.textContent = 'Upload failed. Check the backend server.';
  }
});

askButton.addEventListener('click', async () => {
  const question = questionInput.value.trim();
  if (!question) {
    answer.textContent = 'Please enter some text to analyze.';
    return;
  }

  answer.textContent = 'Thinking...';
  const formData = new FormData();
  formData.append('question', question);
  formData.append('mode', modeSelect.value);

  try {
    const response = await fetch('/api/ask', {
      method: 'POST',
      body: formData,
    });
    const data = await response.json();
    if (!response.ok) {
      answer.textContent = data.detail || 'Request failed.';
      return;
    }
    answer.textContent = data.answer;
  } catch (error) {
    answer.textContent = 'Request failed. Check the backend server.';
  }
});
