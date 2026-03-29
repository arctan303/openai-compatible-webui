/**
 * history.js — localStorage conversation manager
 */

const STORAGE_KEY = 'aichat_conversations';

const History = (() => {
  function load() {
    try {
      return JSON.parse(localStorage.getItem(STORAGE_KEY)) || [];
    } catch { return []; }
  }

  function save(conversations) {
    localStorage.setItem(STORAGE_KEY, JSON.stringify(conversations));
  }

  function getAll() {
    return load().sort((a, b) => new Date(b.updated_at) - new Date(a.updated_at));
  }

  function get(id) {
    return load().find(c => c.id === id) || null;
  }

  function create(title = '新对话') {
    const conv = {
      id: crypto.randomUUID(),
      title,
      created_at: new Date().toISOString(),
      updated_at: new Date().toISOString(),
      messages: [],
    };
    const all = load();
    all.push(conv);
    save(all);
    return conv;
  }

  function addMessage(convId, message) {
    const all = load();
    const conv = all.find(c => c.id === convId);
    if (!conv) return;
    conv.messages.push(message);
    conv.updated_at = new Date().toISOString();
    // Auto-generate title from first user message
    if (conv.messages.length === 1 && message.role === 'user') {
      const text = typeof message.content === 'string'
        ? message.content
        : (message.content.find(c => c.type === 'text')?.text || '新对话');
      conv.title = text.slice(0, 40) + (text.length > 40 ? '…' : '');
    }
    save(all);
    return conv;
  }

  function updateAssistantMessage(convId, content) {
    const all = load();
    const conv = all.find(c => c.id === convId);
    if (!conv) return;
    const last = conv.messages[conv.messages.length - 1];
    if (last && last.role === 'assistant') {
      last.content = content;
      conv.updated_at = new Date().toISOString();
    }
    save(all);
  }

  function remove(id) {
    const all = load().filter(c => c.id !== id);
    save(all);
  }

  function clear() {
    localStorage.removeItem(STORAGE_KEY);
  }

  return { getAll, get, create, addMessage, updateAssistantMessage, remove, clear };
})();
