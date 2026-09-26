const state = {
    conversationId: null,
    conversations: [],
    sending: false,
};

const elements = {
    conversationList: document.getElementById("conversationList"),
    newChatButton: document.getElementById("newChatButton"),
    deleteChatButton: document.getElementById("deleteChatButton"),
    conversationTitle: document.getElementById("conversationTitle"),
    messages: document.getElementById("messages"),
    emptyState: document.getElementById("emptyState"),
    chatForm: document.getElementById("chatForm"),
    messageInput: document.getElementById("messageInput"),
    sendButton: document.getElementById("sendButton"),
    modelBadge: document.getElementById("modelBadge"),
    statusDot: document.getElementById("statusDot"),
    statusText: document.getElementById("statusText"),
    statusDetail: document.getElementById("statusDetail"),
};

function escapeNothing(value) {
    return String(value ?? "");
}

function setEmptyState(visible) {
    if (!elements.emptyState) {
        return;
    }

    elements.emptyState.style.display = visible ? "" : "none";
}

function scrollToBottom() {
    elements.messages.scrollTop = elements.messages.scrollHeight;
}

function createMessageElement(role, content, pending = false) {
    const wrapper = document.createElement("article");
    wrapper.className = "message " + role;

    const avatar = document.createElement("div");
    avatar.className = "avatar";
    avatar.textContent = role === "assistant" ? "AI" : "TÚ";

    const body = document.createElement("div");
    body.className = "message-body";

    const roleLabel = document.createElement("div");
    roleLabel.className = "message-role";
    roleLabel.textContent = role === "assistant" ? "Our AI" : "Tú";

    const messageContent = document.createElement("div");
    messageContent.className = "message-content";

    if (pending) {
        const typing = document.createElement("span");
        typing.className = "typing";

        for (let i = 0; i < 3; i += 1) {
            typing.appendChild(document.createElement("i"));
        }

        messageContent.appendChild(typing);
    } else {
        messageContent.textContent = escapeNothing(content);
    }

    body.append(roleLabel, messageContent);
    wrapper.append(avatar, body);

    return wrapper;
}

function renderMessages(messages) {
    elements.messages
        .querySelectorAll(".message")
        .forEach((node) => node.remove());

    setEmptyState(messages.length === 0);

    for (const message of messages) {
        elements.messages.appendChild(
            createMessageElement(
                message.role,
                message.content,
            )
        );
    }

    scrollToBottom();
}

function renderConversationList() {
    elements.conversationList.replaceChildren();

    if (state.conversations.length === 0) {
        const empty = document.createElement("div");
        empty.className = "conversation-item";
        empty.textContent = "Todavía no hay chats";
        empty.style.cursor = "default";
        elements.conversationList.appendChild(empty);
        return;
    }

    for (const conversation of state.conversations) {
        const button = document.createElement("button");
        button.type = "button";
        button.className = "conversation-item";

        if (conversation.id === state.conversationId) {
            button.classList.add("active");
        }

        button.textContent = conversation.title;
        button.title = conversation.title;

        button.addEventListener("click", () => {
            loadConversation(conversation.id);
        });

        elements.conversationList.appendChild(button);
    }
}

async function requestJson(url, options = {}) {
    const response = await fetch(url, options);

    if (response.status === 204) {
        return null;
    }

    let data;

    try {
        data = await response.json();
    } catch {
        data = {};
    }

    if (!response.ok) {
        throw new Error(
            data.detail || "La solicitud no pudo completarse."
        );
    }

    return data;
}

async function loadHealth() {
    try {
        const health = await requestJson("/health");

        elements.modelBadge.textContent = health.model;

        if (health.database === "connected") {
            elements.statusDot.className = "status-dot online";
            elements.statusText.textContent = "Sistema listo";
            elements.statusDetail.textContent = "PostgreSQL conectado";
        } else {
            elements.statusDot.className = "status-dot degraded";
            elements.statusText.textContent = "Configuración pendiente";
            elements.statusDetail.textContent = "PostgreSQL desconectado";
        }
    } catch {
        elements.statusDot.className = "status-dot degraded";
        elements.statusText.textContent = "Servidor no disponible";
        elements.statusDetail.textContent = "Revisa FastAPI";
    }
}

async function loadConversations() {
    try {
        state.conversations = await requestJson(
            "/v1/conversations"
        );
        renderConversationList();
    } catch {
        state.conversations = [];
        renderConversationList();
    }
}

async function loadConversation(conversationId) {
    if (state.sending) {
        return;
    }

    try {
        const messages = await requestJson(
            "/v1/conversations/" +
                encodeURIComponent(conversationId) +
                "/messages"
        );

        state.conversationId = conversationId;

        const conversation = state.conversations.find(
            (item) => item.id === conversationId
        );

        elements.conversationTitle.textContent =
            conversation?.title || "Conversación";

        elements.deleteChatButton.disabled = false;

        renderMessages(messages);
        renderConversationList();
        elements.messageInput.focus();
    } catch (error) {
        showError(error.message);
    }
}

function newConversation() {
    if (state.sending) {
        return;
    }

    state.conversationId = null;
    elements.conversationTitle.textContent = "Nueva conversación";
    elements.deleteChatButton.disabled = true;
    renderMessages([]);
    renderConversationList();
    elements.messageInput.focus();
}

function showError(message) {
    setEmptyState(false);

    const node = createMessageElement(
        "assistant",
        "Error: " + message
    );
    elements.messages.appendChild(node);
    scrollToBottom();
}

async function sendMessage(message) {
    if (state.sending || !message.trim()) {
        return;
    }

    state.sending = true;
    elements.sendButton.disabled = true;

    setEmptyState(false);

    const userNode = createMessageElement("user", message);
    const pendingNode = createMessageElement(
        "assistant",
        "",
        true
    );

    elements.messages.append(userNode, pendingNode);
    scrollToBottom();

    try {
        const payload = {
            message,
            conversation_id: state.conversationId,
        };

        const result = await requestJson(
            "/v1/chat",
            {
                method: "POST",
                headers: {
                    "Content-Type": "application/json",
                },
                body: JSON.stringify(payload),
            }
        );

        pendingNode.replaceWith(
            createMessageElement(
                "assistant",
                result.response
            )
        );

        state.conversationId = result.conversation_id;
        elements.modelBadge.textContent = result.model;
        elements.deleteChatButton.disabled = false;

        await loadConversations();

        const active = state.conversations.find(
            (item) => item.id === state.conversationId
        );

        elements.conversationTitle.textContent =
            active?.title || "Conversación";

        renderConversationList();
        scrollToBottom();
    } catch (error) {
        pendingNode.remove();
        showError(error.message);
    } finally {
        state.sending = false;
        elements.sendButton.disabled = false;
        elements.messageInput.focus();
    }
}

async function deleteCurrentConversation() {
    if (!state.conversationId || state.sending) {
        return;
    }

    const confirmed = window.confirm(
        "¿Eliminar esta conversación y todos sus mensajes?"
    );

    if (!confirmed) {
        return;
    }

    try {
        await requestJson(
            "/v1/conversations/" +
                encodeURIComponent(state.conversationId),
            {
                method: "DELETE",
            }
        );

        await loadConversations();
        newConversation();
    } catch (error) {
        showError(error.message);
    }
}

function resizeInput() {
    elements.messageInput.style.height = "auto";
    elements.messageInput.style.height =
        Math.min(elements.messageInput.scrollHeight, 170) + "px";
}

elements.chatForm.addEventListener("submit", (event) => {
    event.preventDefault();

    const message = elements.messageInput.value.trim();

    if (!message) {
        return;
    }

    elements.messageInput.value = "";
    resizeInput();
    sendMessage(message);
});

elements.messageInput.addEventListener("input", resizeInput);

elements.messageInput.addEventListener("keydown", (event) => {
    if (
        event.key === "Enter" &&
        !event.shiftKey
    ) {
        event.preventDefault();
        elements.chatForm.requestSubmit();
    }
});

elements.newChatButton.addEventListener(
    "click",
    newConversation
);

elements.deleteChatButton.addEventListener(
    "click",
    deleteCurrentConversation
);

document.querySelectorAll(".suggestion").forEach((button) => {
    button.addEventListener("click", () => {
        elements.messageInput.value = button.textContent.trim();
        resizeInput();
        elements.messageInput.focus();
    });
});

async function bootstrap() {
    await Promise.all([
        loadHealth(),
        loadConversations(),
    ]);

    newConversation();
}

bootstrap();
