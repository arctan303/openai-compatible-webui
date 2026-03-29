/**
 * chat.js — React Demo Integrated Interface Logic
 */

// ─── State ────────────────────────────────────────────────────────────────────
let currentUser = null;
let currentConvId = null;
let isStreaming = false;
let abortController = null;
let pendingAttachments = [];
let allConvs = [];
let selectedModelId = null;
let modelDisplayMap = {};

// ─── DOM refs ─────────────────────────────────────────────────────────────────
const sidebar         = document.getElementById('sidebar');
const sidebarOpen     = document.getElementById('sidebar-open');
const sidebarClose    = document.getElementById('sidebar-close');
const historyList     = document.getElementById('history-list');
const historyEmpty    = document.getElementById('history-empty');
const newChatBtn      = document.getElementById('new-chat-btn');
const searchInput     = document.getElementById('search-input');
const userAvatar      = document.getElementById('user-avatar');
const userNameDisplay = document.getElementById('user-name');
const dropdownAvatar  = document.getElementById('dropdown-avatar');
const dropdownName    = document.getElementById('dropdown-name');
const userBtn         = document.getElementById('user-btn');
const userMenu        = document.getElementById('user-menu');
const adminLink       = document.getElementById('admin-link');
const adminDivider    = document.querySelector('.admin-divider');
const logoutBtn       = document.getElementById('logout-btn');
const modelPillBtn    = document.getElementById('model-pill-btn');
const modelDropdown   = document.getElementById('model-dropdown');
const modelDropdownList = document.getElementById('model-dropdown-list');
const modelPillLabel  = document.getElementById('model-pill-label');
const sidebarBackdrop = document.getElementById('sidebar-backdrop');
const messagesWrapper = document.getElementById('messages-wrapper');
const messagesContainer = document.getElementById('messages-container');
const emptyState      = document.getElementById('empty-state');
const chatInput       = document.getElementById('chat-input');
const sendBtn         = document.getElementById('send-btn');
const sendIcon        = document.getElementById('send-icon');
const stopIcon        = document.getElementById('stop-icon');
const attachBtn       = document.getElementById('attach-btn');
const fileInput       = document.getElementById('file-input');
const attachStrip     = document.getElementById('attachment-strip');

// ─── marked setup ─────────────────────────────────────────────────────────────
function setupMarked() {
  if (typeof window.marked === 'undefined') return;
  marked.setOptions({ breaks: true, gfm: true });
  const renderer = new marked.Renderer();
  renderer.code = (code, lang) => {
    const language = lang || 'plaintext';
    let highlighted;
    try {
      const codeText = typeof code === 'object' ? code.text : code;
      highlighted = hljs.highlight(codeText, {
        language: hljs.getLanguage(language) ? language : 'plaintext'
      }).value;
    } catch {
      highlighted = typeof code === 'object' ? code.text : String(code);
    }
    return `<div class="relative bg-gray-900 rounded-lg overflow-hidden my-4 group">
      <div class="flex items-center justify-between px-4 py-1.5 bg-gray-800 text-xs text-gray-400">
        <span>${language}</span>
        <button class="flex items-center gap-1.5 hover:text-white transition-colors" onclick="copyCode(this)">
          <i data-lucide="copy" class="w-3.5 h-3.5"></i> <span>Copy</span>
        </button>
      </div>
      <div class="overflow-x-auto p-4 text-sm text-gray-300 pointer-events-auto">
        <pre><code class="hljs">${highlighted}</code></pre>
      </div>
    </div>`;
  };
  marked.use({ renderer });
}

window.addEventListener('DOMContentLoaded', () => {
    setupMarked();
    if (window.lucide) window.lucide.createIcons();
});

window.copyCode = function(btn) {
  const wrapper = btn.closest('.group');
  const code = wrapper.querySelector('code').innerText;
  navigator.clipboard.writeText(code).then(() => {
    const span = btn.querySelector('span');
    span.textContent = 'Copied!';
    setTimeout(() => { span.textContent = 'Copy'; }, 2000);
  });
};

function parseMarkdown(text) {
  if (typeof marked === 'undefined') return esc(text).replace(/\n/g, '<br>');
  const html = marked.parse(text);
  // Re-run lucide icons for any icons spawned
  setTimeout(() => window.lucide && window.lucide.createIcons(), 0);
  return html;
}

// ─── Helpers ──────────────────────────────────────────────────────────────────
function esc(s) {
  return String(s).replace(/&/g,'&amp;').replace(/</g,'&lt;').replace(/>/g,'&gt;');
}

function getModelLabel(modelId) {
  if (!modelId) return '模型';
  return modelDisplayMap[modelId] || modelId;
}

function scrollToBottom(smooth = true) {
  messagesWrapper.scrollTo({ top: messagesWrapper.scrollHeight, behavior: smooth ? 'smooth' : 'instant' });
}

function autoResize() {
  chatInput.style.height = 'auto';
  chatInput.style.height = Math.min(chatInput.scrollHeight, 192) + 'px'; // ~48 max-h
  updateSendBtn();
}

function updateSendBtn() {
  const hasText = chatInput.value.trim().length > 0;
  const hasAttach = pendingAttachments.length > 0;
  const isUploading = pendingAttachments.some(a => a.isUploading);
  
  if (isStreaming) {
      sendBtn.disabled = true;
      sendBtn.classList.add('bg-[#e5e5e5]', 'hover:bg-[#d5d5d5]');
      sendBtn.classList.remove('bg-black', 'text-white');
  } else if ((hasText || hasAttach) && !isUploading) {
      sendBtn.disabled = false;
      sendBtn.classList.remove('bg-[#e5e5e5]', 'hover:bg-[#d5d5d5]', 'cursor-not-allowed');
      sendBtn.classList.add('bg-black', 'text-white');
      sendIcon.classList.remove('hidden');
      stopIcon.classList.add('hidden');
  } else {
      sendBtn.disabled = true;
      sendBtn.classList.add('bg-[#e5e5e5]', 'hover:bg-[#d5d5d5]');
      sendBtn.classList.remove('bg-black', 'text-white');
  }
}

// ... skip unchanged functions until uploadFile

async function uploadFile(file) {
  const isImage = file.type.startsWith('image/');
  const attachId = Math.random().toString(36).substring(7);
  
  // Create placeholder immediately so user sees uploading state
  const placeholder = { id: attachId, type: isImage ? 'image' : 'text', name: file.name, isUploading: true };
  if (isImage) {
      placeholder.data = URL.createObjectURL(file); // Show local preview instantly
  }
  pendingAttachments.push(placeholder);
  renderAttachStrip();
  updateSendBtn();
  
  if (isImage) {
      try {
          const dataUrl = await compressImage(file);
          const attach = pendingAttachments.find(a => a.id === attachId);
          if (attach) {
              attach.data = dataUrl;
              attach.mime = file.type;
              attach.isUploading = false;
          }
      } catch (e) {
          pendingAttachments = pendingAttachments.filter(a => a.id !== attachId);
          alert('图片处理失败');
      }
      renderAttachStrip();
      updateSendBtn();
      return;
  }

  const formData = new FormData();
  formData.append('file', file);
  try {
    const res = await fetch('/api/upload', { method: 'POST', body: formData });
    if (!res.ok) throw new Error();
    const attachment = await res.json();
    const attachIdx = pendingAttachments.findIndex(a => a.id === attachId);
    if (attachIdx >= 0) {
        pendingAttachments.splice(attachIdx, 1, { ...attachment, id: attachId, isUploading: false });
    }
    renderAttachStrip();
    updateSendBtn();
  } catch (err) {
    pendingAttachments = pendingAttachments.filter(a => a.id !== attachId);
    renderAttachStrip();
    updateSendBtn();
    alert('上传失败');
  }
}

function compressImage(file) {
    return new Promise((resolve) => {
        const reader = new FileReader();
        reader.onload = (e) => {
            const img = new Image();
            img.onload = () => {
                const canvas = document.createElement('canvas');
                let width = img.width;
                let height = img.height;
                if (width > 1200 || height > 1200) {
                    const ratio = Math.min(1200 / width, 1200 / height);
                    width = width * ratio;
                    height = height * ratio;
                }
                canvas.width = width;
                canvas.height = height;
                const ctx = canvas.getContext('2d');
                ctx.drawImage(img, 0, 0, width, height);
                // Artificial delay to show uploading UI (e.g. 500ms) to ensure UX feedback is visible
                setTimeout(() => {
                    resolve(canvas.toDataURL('image/jpeg', 0.6));
                }, 500);
            };
            img.src = e.target.result;
        };
        reader.readAsDataURL(file);
    });
}

function renderAttachStrip() {
  attachStrip.innerHTML = '';
  pendingAttachments.forEach((a, i) => {
    const thumb = document.createElement('div');
    thumb.className = 'relative inline-flex items-center justify-center shrink-0 border border-gray-200 rounded-lg overflow-hidden bg-white mr-2 mb-2 p-2 shadow-sm gap-2';
    
    if (a.type === 'image') {
      thumb.innerHTML = `<img src="${a.data}" class="h-10 w-10 object-cover rounded opacity-${a.isUploading ? '50' : '100'} transition-opacity" alt="" />`;
    } else {
      thumb.innerHTML = `<div class="bg-blue-100 p-2 rounded opacity-${a.isUploading ? '50' : '100'}"><i data-lucide="file-text" class="w-6 h-6 text-blue-500"></i></div>
                         <div class="flex flex-col opacity-${a.isUploading ? '50' : '100'}"><span class="text-xs font-medium max-w-[80px] truncate">${esc(a.name)}</span></div>`;
    }

    if (a.isUploading) {
        // Loading spinner overlay
        const spinner = document.createElement('div');
        spinner.className = 'absolute inset-0 flex items-center justify-center bg-white/40';
        spinner.innerHTML = `<i data-lucide="loader-2" class="w-5 h-5 text-gray-800 animate-spin"></i>`;
        thumb.appendChild(spinner);
    } else {
        const rm = document.createElement('button');
        rm.className = 'absolute -top-1.5 -right-1.5 w-4 h-4 bg-gray-600 text-white rounded-full flex items-center justify-center text-[10px] hover:bg-red-500 z-10';
        rm.innerHTML = '✕';
        rm.addEventListener('click', () => {
          pendingAttachments.splice(i, 1);
          renderAttachStrip();
          updateSendBtn();
        });
        thumb.appendChild(rm);
    }
    attachStrip.appendChild(thumb);
  });
  if (window.lucide) window.lucide.createIcons();
}

function setStreaming(state) {
  isStreaming = state;
  chatInput.disabled = state;
  updateSendBtn();
}

// ─── Auth ─────────────────────────────────────────────────────────────────────
async function loadUser() {
  try {
    const res = await fetch('/api/auth/me');
    if (!res.ok) { window.location.href = '/'; return; }
    currentUser = await res.json();
    modelDisplayMap = currentUser.model_aliases || {};
    const shortName = currentUser.username.substring(0, 2).toUpperCase();
    userNameDisplay.textContent = currentUser.username;
    dropdownName.textContent = currentUser.username;
    userAvatar.textContent = shortName;
    dropdownAvatar.textContent = shortName;
    
    if (currentUser.is_admin) {
        adminLink.classList.remove('hidden');
        adminDivider.classList.remove('hidden');
    }
  } catch {
    window.location.href = '/';
  }
}

// ─── Models ───────────────────────────────────────────────────────────────────
async function loadModels() {
  try {
    const res = await fetch('/api/models');
    if (!res.ok) throw new Error();
    const data = await res.json();
    let models = data.data || [];

    modelDropdownList.innerHTML = '';
    if (models.length === 0) {
        const fallbackId = currentUser?.model || 'gpt-4o';
        models = [{ id: fallbackId, display_name: getModelLabel(fallbackId) }];
    }
    
    models.forEach(m => {
        if (m.display_name) {
            modelDisplayMap[m.id] = m.display_name;
        }
        const item = document.createElement('div');
        item.className = 'px-4 py-3 mx-2 my-1 hover:bg-gray-100 rounded-lg cursor-pointer flex items-center text-sm font-medium text-gray-800 transition-colors gap-3';
        item.innerHTML = `<i data-lucide="sparkles" class="w-4 h-4 text-sky-500"></i><span class="truncate">${esc(m.display_name || getModelLabel(m.id))}</span>`;
        item.onclick = (e) => {
            e.stopPropagation();
            selectedModelId = m.id;
            modelPillLabel.textContent = getModelLabel(m.id);
            modelDropdown.classList.add('hidden');
        };
        modelDropdownList.appendChild(item);
        
        if (!selectedModelId && m.id === currentUser?.model) selectedModelId = m.id;
    });
    
    if (!selectedModelId && models.length > 0) selectedModelId = models[0].id;
    modelPillLabel.textContent = getModelLabel(selectedModelId);
    
    if (window.lucide) window.lucide.createIcons();
  } catch {
    selectedModelId = currentUser?.model || 'gpt-4o';
    modelPillLabel.textContent = getModelLabel(selectedModelId);
  }
}

modelPillBtn.addEventListener('click', (e) => {
  e.stopPropagation();
  modelDropdown.classList.toggle('hidden');
});

// ─── Sidebar toggle ───────────────────────────────────────────────────────────
function closeSidebar() {
    sidebar.classList.remove('w-[260px]', 'border-r');
    sidebar.classList.add('w-0');
    sidebarOpen.classList.remove('hidden');
    sidebarBackdrop.classList.add('hidden');
}

function openSidebar() {
    sidebar.classList.remove('w-0');
    sidebar.classList.add('w-[260px]', 'border-r');
    sidebarOpen.classList.add('hidden');
    sidebarBackdrop.classList.remove('hidden');
}

sidebarClose.addEventListener('click', closeSidebar);
sidebarOpen.addEventListener('click', openSidebar);
sidebarBackdrop.addEventListener('click', closeSidebar);

// ─── User dropdown ────────────────────────────────────────────────────────────
userBtn.addEventListener('click', (e) => {
  e.stopPropagation();
  userMenu.classList.toggle('hidden');
});

document.addEventListener('click', (e) => {
  if (!userMenu.contains(e.target) && !userBtn.contains(e.target)) {
      userMenu.classList.add('hidden');
  }
  if (!modelPillBtn.contains(e.target) && modelDropdown && !modelDropdown.contains(e.target)) {
      modelDropdown.classList.add('hidden');
  }
});

adminLink.addEventListener('click', () => { window.location.href = '/admin'; });
logoutBtn.addEventListener('click', async () => {
  await fetch('/api/auth/logout', { method: 'POST' });
  window.location.href = '/';
});

// ─── History sidebar ──────────────────────────────────────────────────────────
function renderHistorySidebar(filter = '') {
  allConvs = History.getAll();
  const filtered = filter
    ? allConvs.filter(c => (c.title || '').toLowerCase().includes(filter.toLowerCase()))
    : allConvs;

  historyList.querySelectorAll('.history-item').forEach(el => el.remove());
  historyEmpty.classList.toggle('hidden', filtered.length > 0);

  filtered.forEach(conv => {
    const item = document.createElement('div');
    const isActive = conv.id === currentConvId;
    item.className = `history-item flex items-center px-2 py-2 rounded-lg cursor-pointer transition-colors group ${isActive ? 'bg-gray-200' : 'hover:bg-gray-200'}`;
    item.innerHTML = `
      <span class="truncate ${isActive ? 'text-gray-900 font-medium' : 'text-gray-700'} flex-1">${esc(conv.title || '新对话')}</span>
      <button class="history-item-del opacity-0 group-hover:opacity-100 p-1 text-gray-500 hover:text-red-500 transition-opacity">
        <i data-lucide="trash-2" class="w-4 h-4"></i>
      </button>
    `;

    item.querySelector('.history-item-del').addEventListener('click', async (e) => {
      e.stopPropagation();
      await History.remove(conv.id);
      if (currentConvId === conv.id) startNewChat();
      else renderHistorySidebar(searchInput.value);
    });

    item.addEventListener('click', () => loadConversation(conv.id));
    historyList.appendChild(item);
  });
  if (window.lucide) window.lucide.createIcons();
}

searchInput.addEventListener('input', () => renderHistorySidebar(searchInput.value));

// ─── Chat Lifecycle ───────────────────────────────────────────────────────────
function startNewChat() {
  currentConvId = null;
  messagesContainer.querySelectorAll('.message-row').forEach(e => e.remove());
  emptyState.classList.remove('hidden');
  pendingAttachments = [];
  renderAttachStrip();
  renderHistorySidebar(searchInput.value);
  chatInput.value = '';
  chatInput.style.height = 'auto';
  updateSendBtn();
  chatInput.focus();
}

newChatBtn.addEventListener('click', startNewChat);

function loadConversation(id) {
  const conv = History.get(id);
  if (!conv) return;
  currentConvId = id;
  messagesContainer.querySelectorAll('.message-row').forEach(e => e.remove());
  emptyState.classList.add('hidden');
  conv.messages.forEach(msg => renderMessage(msg.role, msg.content, msg.attachments));
  
  // Sync Model Pill
  if (conv.model) {
      selectedModelId = conv.model;
      modelPillLabel.textContent = getModelLabel(conv.model);
  }
  
  scrollToBottom(false);
  renderHistorySidebar(searchInput.value);
}

// ─── Render messages ──────────────────────────────────────────────────────────
function renderMessage(role, content, attachments = []) {
  emptyState.classList.add('hidden');

  const wrap = document.createElement('div');
  wrap.className = 'message-row w-full mb-8';

  if (role === 'user') {
    let attachHtml = '';
    if (attachments && attachments.length) {
      const items = attachments.map(a => {
        if (a.type === 'image') return `<img src="${a.data}" class="w-16 h-16 object-cover rounded shadow-sm border border-gray-200 bg-white" alt="img" />`;
        return `<div class="flex items-center gap-2 bg-white border border-gray-200 rounded-xl px-3 py-2 shadow-sm"><i data-lucide="file" class="w-4 h-4 text-blue-500"></i><span class="text-xs font-medium">${esc(a.name)}</span></div>`;
      }).join('');
      attachHtml = `<div class="flex flex-wrap gap-2 mb-2 justify-end w-full">${items}</div>`;
    }

    const text = typeof content === 'string' ? content : (Array.isArray(content) ? content.find(c => c.type === 'text')?.text || '' : '');

    wrap.innerHTML = `
      <div class="flex justify-end w-full">
          <div class="flex flex-col items-end max-w-[80%]">
              ${attachHtml}
              <div class="bg-[#f4f4f4] px-5 py-3 rounded-2xl rounded-tr-sm text-[15px] leading-relaxed text-gray-800 break-words whitespace-pre-wrap">${esc(text)}</div>
          </div>
      </div>
    `;
  } else {
    const text = typeof content === 'string' ? content : '';
    wrap.innerHTML = `
      <div class="flex justify-start w-full group">
          <div class="w-8 h-8 rounded-full border border-gray-200 flex items-center justify-center shrink-0 mr-4 font-bold tracking-tighter text-sm pb-0.5">✦</div>
          <div class="flex-1 min-w-0 text-[15.5px] leading-relaxed text-gray-800 markdown-body">
              ${parseMarkdown(text)}
          </div>
      </div>
    `;
  }

  messagesContainer.appendChild(wrap);
  if (window.lucide) window.lucide.createIcons();
  return wrap;
}

function createAssistantMessage() {
  emptyState.classList.add('hidden');
  const wrap = document.createElement('div');
  wrap.className = 'message-row w-full mb-8';
  wrap.innerHTML = `
    <div class="flex justify-start w-full group">
        <div class="w-8 h-8 rounded-full border border-gray-200 flex items-center justify-center shrink-0 mr-4 font-bold tracking-tighter text-sm pb-0.5">✦</div>
        <div class="flex-1 min-w-0 text-[15.5px] leading-relaxed text-gray-800 markdown-body">
            <span class="cursor"></span>
        </div>
    </div>
  `;
  messagesContainer.appendChild(wrap);
  return wrap.querySelector('.markdown-body');
}

// ─── Send logic ─────────────────────────────────────────────────────────────
async function sendMessage() {
  if (isStreaming) {
    abortController?.abort();
    return;
  }

  const text = chatInput.value.trim();
  if (!text && pendingAttachments.length === 0) return;

  if (!currentConvId) {
    const modelToUse = selectedModelId || currentUser?.model || 'gpt-4o';
    const conv = await History.create('新对话', modelToUse);
    currentConvId = conv.id;
  }

  const attachmentsCopy = [...pendingAttachments];
  let userContent;

  if (attachmentsCopy.some(a => a.type === 'image') && text) {
    userContent = [{ type: 'text', text }];
    attachmentsCopy.filter(a => a.type === 'image').forEach(a => {
      userContent.push({ type: 'image_url', image_url: { url: a.data } });
    });
  } else {
    let fullText = text;
    attachmentsCopy.filter(a => a.type === 'text').forEach(a => {
      fullText += `\n\n---\n文件: ${a.name}\n\`\`\`\n${a.content}\n\`\`\``;
    });
    userContent = fullText;
  }

  await History.addMessage(currentConvId, { role: 'user', content: userContent, attachments: attachmentsCopy }, selectedModelId);
  renderMessage('user', userContent, attachmentsCopy);

  chatInput.value = '';
  chatInput.style.height = 'auto';
  pendingAttachments = [];
  renderAttachStrip();
  updateSendBtn();

  const conv = History.get(currentConvId);
  const apiMessages = (conv?.messages || []).map(m => ({ role: m.role, content: m.content }));
  const selectedModel = selectedModelId || currentUser?.model || 'gpt-4o';

  setStreaming(true);
  scrollToBottom();

  const contentEl = createAssistantMessage();
  scrollToBottom();

  abortController = new AbortController();
  let fullText = '';

  try {
    const res = await fetch('/api/chat/stream', {
      method: 'POST',
      headers: { 'Content-Type': 'application/json' },
      body: JSON.stringify({ messages: apiMessages, model: selectedModel }),
      signal: abortController.signal,
    });

    if (!res.ok) throw new Error((await res.json().catch(()=>({}))).detail || '请求失败');

    const reader = res.body.getReader();
    const decoder = new TextDecoder();
    let buffer = '';

    while (true) {
      const { done, value } = await reader.read();
      if (done) break;

      buffer += decoder.decode(value, { stream: true });
      const lines = buffer.split('\n');
      buffer = lines.pop();

      for (const line of lines) {
        if (!line.startsWith('data:')) continue;
        const data = line.slice(5).trim();
        if (data === '[DONE]') break;
        if (!data) continue;

        try {
          const json = JSON.parse(data);
          if (json.error) throw new Error(json.error);
          const delta = json.choices?.[0]?.delta?.content;
          if (delta) {
            fullText += delta;
            contentEl.innerHTML = parseMarkdown(fullText) + '<span class="cursor"></span>';
            scrollToBottom(false);
          }
        } catch (e) {
          if (e.message !== 'Unexpected end of JSON input') console.warn('parse:', e);
        }
      }
    }
  } catch (err) {
    if (err.name !== 'AbortError') {
      contentEl.innerHTML = `<p class="text-red-500">⚠️ ${esc(err.message)}</p>`;
    }
  } finally {
    contentEl.querySelector('.cursor')?.remove();
    if (!fullText && !abortController.signal.aborted) {
      contentEl.innerHTML = '<p class="text-gray-400">（已停止）</p>';
    } else if (fullText) {
      contentEl.innerHTML = parseMarkdown(fullText);
    }
    if (fullText) await History.addMessage(currentConvId, { role: 'assistant', content: fullText }, selectedModelId);

    // AI Title Generation (Background)
    const currentConv = History.get(currentConvId);
    if (currentConv && currentConv.messages.length === 2) {
        (async () => {
            try {
                const titleRes = await fetch(`/api/history/${currentConvId}/generate_title`, {
                   method: 'POST',
                   headers: { 'Content-Type': 'application/json' },
                   body: JSON.stringify({ messages: currentConv.messages, model: selectedModelId })
                });
                if (titleRes.ok) {
                    const data = await titleRes.json();
                    if (data.title) {
                        currentConv.title = data.title;
                        renderHistorySidebar(searchInput.value);
                    }
                }
            } catch (e) { console.warn('Title gen failed', e); }
        })();
    }

    setStreaming(false);
    renderHistorySidebar(searchInput.value);
    scrollToBottom();
    updateSendBtn();
  }
}

// ─── Input events ─────────────────────────────────────────────────────────────
chatInput.addEventListener('input', autoResize);

chatInput.addEventListener('paste', async (e) => {
    const items = e.clipboardData.items;
    for (const item of items) {
        if (item.type.indexOf('image/') !== -1) {
            e.preventDefault();
            const file = item.getAsFile();
            if (file) await uploadFile(file);
        }
    }
});

chatInput.addEventListener('keydown', (e) => {
  if (e.key === 'Enter' && !e.shiftKey) {
    if (chatInput.value.trim() !== '' || pendingAttachments.length > 0) {
        e.preventDefault();
        sendMessage();
    }
  }
});

sendBtn.addEventListener('click', sendMessage);

// ─── Attachments ──────────────────────────────────────────────────────────────
attachBtn.addEventListener('click', () => fileInput.click());

fileInput.addEventListener('change', async () => {
  for (const file of Array.from(fileInput.files || [])) {
    await uploadFile(file);
  }
  fileInput.value = '';
});

// ─── Init ─────────────────────────────────────────────────────────────────────
let wasMobile = window.innerWidth <= 768;

window.addEventListener('resize', () => {
  const isMobile = window.innerWidth <= 768;
  if (isMobile !== wasMobile) {
    if (isMobile) {
      closeSidebar();
    } else {
      openSidebar();
    }
    wasMobile = isMobile;
  }
});

(async () => {
  await loadUser();
  await loadModels();
  await History.loadFromServer();
  renderHistorySidebar();
  
  if (wasMobile) {
      closeSidebar();
  }
  
  chatInput.focus();
  updateSendBtn();
})();
