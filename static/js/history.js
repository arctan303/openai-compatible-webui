/**
 * history.js — Cloud-synced conversation manager
 */

const History = (() => {
  let conversations = [];

  function createConversationId() {
    if (window.crypto && typeof window.crypto.randomUUID === 'function') {
      return window.crypto.randomUUID();
    }

    // Fallback for older browsers or restricted environments.
    const rand = () => Math.random().toString(16).slice(2, 10);
    return `${Date.now().toString(16)}-${rand()}-${rand()}`;
  }

  async function loadFromServer() {
    try {
      const res = await fetch('/api/history');
      if (res.ok) {
        conversations = await res.json();
      }
    } catch (e) {
      console.error('Failed to load history from cloud', e);
    }
    return conversations;
  }

  function getAll() {
    return conversations;
  }

  function get(id) {
    return conversations.find(c => c.id === id) || null;
  }

  async function create(title = '新对话', model = 'gpt-4o') {
    const conv = {
      id: createConversationId(),
      title,
      messages: [],
      model,
      created_at: new Date().toISOString(),
      updated_at: new Date().toISOString()
    };
    conversations.unshift(conv);
    saveToServer(conv);
    return conv;
  }

  async function saveToServer(conv) {
    try {
      await fetch(`/api/history/${conv.id}`, {
        method: 'POST',
        headers: { 'Content-Type': 'application/json' },
        body: JSON.stringify({ title: conv.title, messages: conv.messages, model: conv.model })
      });
    } catch (e) {
      console.error('Failed to sync history to cloud', e);
    }
  }

  async function addMessage(convId, message, model = null) {
    const conv = conversations.find(c => c.id === convId);
    if (!conv) return;
    conv.messages.push(message);
    if (model) conv.model = model;
    conv.updated_at = new Date().toISOString();
    
    // Auto-generate title from first user message
    if (conv.messages.length === 1 && message.role === 'user') {
      const text = typeof message.content === 'string'
        ? message.content
        : (message.content.find(c => c.type === 'text')?.text || '新对话');
      conv.title = text.slice(0, 40) + (text.length > 40 ? '…' : '');
    }
    
    // Sort to top
    conversations = [conv, ...conversations.filter(c => c.id !== conv.id)];
    
    saveToServer(conv);
    return conv;
  }

  async function updateAssistantMessage(convId, content) {
    const conv = conversations.find(c => c.id === convId);
    if (!conv) return;
    const last = conv.messages[conv.messages.length - 1];
    if (last && last.role === 'assistant') {
      last.content = content;
      conv.updated_at = new Date().toISOString();
      saveToServer(conv);
    }
  }

  async function remove(id) {
    conversations = conversations.filter(c => c.id !== id);
    try {
      await fetch(`/api/history/${id}`, { method: 'DELETE' });
    } catch (e) {
      console.error('Delete sync failed', e);
    }
  }

  function clear() {
    conversations = [];
  }

  return { loadFromServer, getAll, get, create, addMessage, updateAssistantMessage, remove, clear };
})();
