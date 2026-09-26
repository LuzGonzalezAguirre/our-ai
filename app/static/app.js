const state = {
    conversationId: null,
    conversations: [],
    projects: [],
    projectId: null,
    knowledge: [],
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
    ragBadge: document.getElementById("ragBadge"),
    statusDot: document.getElementById("statusDot"),
    statusText: document.getElementById("statusText"),
    statusDetail: document.getElementById("statusDetail"),
    projectSelect: document.getElementById("projectSelect"),
    projectEyebrow: document.getElementById("projectEyebrow"),
    newProjectButton: document.getElementById("newProjectButton"),
    knowledgeButton: document.getElementById("knowledgeButton"),
    projectModal: document.getElementById("projectModal"),
    projectForm: document.getElementById("projectForm"),
    projectName: document.getElementById("projectName"),
    projectDescription: document.getElementById("projectDescription"),
    knowledgeModal: document.getElementById("knowledgeModal"),
    knowledgeForm: document.getElementById("knowledgeForm"),
    knowledgeTitle: document.getElementById("knowledgeTitle"),
    knowledgeContent: document.getElementById("knowledgeContent"),
    knowledgeSubmitButton: document.getElementById("knowledgeSubmitButton"),
    knowledgeList: document.getElementById("knowledgeList"),
    knowledgeProjectTitle: document.getElementById("knowledgeProjectTitle"),
};

function setEmptyState(visible) {
    elements.emptyState.style.display = visible ? "" : "none";
}

function scrollToBottom() {
    elements.messages.scrollTop = elements.messages.scrollHeight;
}

function currentProject() {
    return state.projects.find(
        (project) => project.id === state.projectId
    );
}

function updateProjectHeader() {
    const project = currentProject();
    elements.projectEyebrow.textContent =
        (project?.name || "PROJECT").toUpperCase();
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
        messageContent.textContent = String(content ?? "");
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

function renderProjects() {
    elements.projectSelect.replaceChildren();

    for (const project of state.projects) {
        const option = document.createElement("option");
        option.value = project.id;
        option.textContent = project.name;
        elements.projectSelect.appendChild(option);
    }

    if (state.projectId) {
        elements.projectSelect.value = state.projectId;
    }

    updateProjectHeader();
}

function renderKnowledge() {
    elements.knowledgeList.replaceChildren();

    if (state.knowledge.length === 0) {
        const empty = document.createElement("div");
        empty.className = "knowledge-empty";
        empty.textContent = "Este proyecto todavía no tiene conocimiento.";
        elements.knowledgeList.appendChild(empty);
        return;
    }

    for (const source of state.knowledge) {
        const row = document.createElement("div");
        row.className = "knowledge-item";

        const info = document.createElement("div");

        const title = document.createElement("strong");
        title.textContent = source.title;

        const meta = document.createElement("span");
        meta.textContent =
            source.chunk_count +
            (source.chunk_count === 1 ? " fragmento" : " fragmentos");

        info.append(title, meta);

        const remove = document.createElement("button");
        remove.type = "button";
        remove.className = "knowledge-delete";
        remove.textContent = "×";
        remove.title = "Eliminar fuente";

        remove.addEventListener("click", async () => {
            const confirmed = window.confirm(
                "¿Eliminar esta fuente de conocimiento?"
            );

            if (!confirmed) {
                return;
            }

            try {
                await requestJson(
                    "/v1/projects/" +
                        encodeURIComponent(state.projectId) +
                        "/knowledge/" +
                        encodeURIComponent(source.id),
                    { method: "DELETE" }
                );
                await loadKnowledge();
            } catch (error) {
                window.alert(error.message);
            }
        });

        row.append(info, remove);
        elements.knowledgeList.appendChild(row);
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
        elements.ragBadge.textContent =
            health.embedding_model || "RAG local";

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

async function loadProjects(preferredProjectId = null) {
    state.projects = await requestJson("/v1/projects");

    const projectExists = state.projects.some(
        (project) => project.id === preferredProjectId
    );

    if (projectExists) {
        state.projectId = preferredProjectId;
    } else if (
        !state.projects.some(
            (project) => project.id === state.projectId
        )
    ) {
        state.projectId = state.projects[0]?.id || null;
    }

    renderProjects();
}

async function loadConversations() {
    if (!state.projectId) {
        state.conversations = [];
        renderConversationList();
        return;
    }

    try {
        state.conversations = await requestJson(
            "/v1/conversations?project_id=" +
                encodeURIComponent(state.projectId)
        );
        renderConversationList();
    } catch {
        state.conversations = [];
        renderConversationList();
    }
}

async function loadKnowledge() {
    if (!state.projectId) {
        state.knowledge = [];
        renderKnowledge();
        return;
    }

    state.knowledge = await requestJson(
        "/v1/projects/" +
            encodeURIComponent(state.projectId) +
            "/knowledge"
    );

    renderKnowledge();
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
    if (
        state.sending ||
        !message.trim() ||
        !state.projectId
    ) {
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
            project_id: state.projectId,
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
        elements.ragBadge.textContent =
            result.knowledge_chunks_used > 0
                ? result.knowledge_chunks_used + " chunks"
                : "RAG local";
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

function openModal(modal) {
    modal.hidden = false;
    document.body.classList.add("modal-open");
}

function closeModal(modal) {
    modal.hidden = true;

    if (
        elements.projectModal.hidden &&
        elements.knowledgeModal.hidden
    ) {
        document.body.classList.remove("modal-open");
    }
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

elements.newChatButton.addEventListener("click", newConversation);

elements.deleteChatButton.addEventListener(
    "click",
    deleteCurrentConversation
);

elements.projectSelect.addEventListener("change", async () => {
    state.projectId = elements.projectSelect.value;
    updateProjectHeader();
    newConversation();
    await loadConversations();
});

elements.newProjectButton.addEventListener("click", () => {
    elements.projectForm.reset();
    openModal(elements.projectModal);
    elements.projectName.focus();
});

elements.knowledgeButton.addEventListener("click", async () => {
    const project = currentProject();
    elements.knowledgeProjectTitle.textContent =
        project ? "Conocimiento · " + project.name : "Conocimiento";

    await loadKnowledge();
    openModal(elements.knowledgeModal);
    elements.knowledgeTitle.focus();
});

elements.projectForm.addEventListener("submit", async (event) => {
    event.preventDefault();

    try {
        const project = await requestJson(
            "/v1/projects",
            {
                method: "POST",
                headers: {
                    "Content-Type": "application/json",
                },
                body: JSON.stringify({
                    name: elements.projectName.value.trim(),
                    description:
                        elements.projectDescription.value.trim(),
                }),
            }
        );

        await loadProjects(project.id);
        await loadConversations();
        newConversation();
        closeModal(elements.projectModal);
    } catch (error) {
        window.alert(error.message);
    }
});

elements.knowledgeForm.addEventListener(
    "submit",
    async (event) => {
        event.preventDefault();

        if (!state.projectId) {
            return;
        }

        const originalText =
            elements.knowledgeSubmitButton.textContent;

        elements.knowledgeSubmitButton.disabled = true;
        elements.knowledgeSubmitButton.textContent =
            "Vectorizando...";

        try {
            await requestJson(
                "/v1/projects/" +
                    encodeURIComponent(state.projectId) +
                    "/knowledge",
                {
                    method: "POST",
                    headers: {
                        "Content-Type": "application/json",
                    },
                    body: JSON.stringify({
                        title: elements.knowledgeTitle.value.trim(),
                        content: elements.knowledgeContent.value.trim(),
                    }),
                }
            );

            elements.knowledgeForm.reset();
            await loadKnowledge();
        } catch (error) {
            window.alert(error.message);
        } finally {
            elements.knowledgeSubmitButton.disabled = false;
            elements.knowledgeSubmitButton.textContent =
                originalText;
        }
    }
);

document.querySelectorAll("[data-close-modal]").forEach((button) => {
    button.addEventListener("click", () => {
        const modal = document.getElementById(
            button.dataset.closeModal
        );
        closeModal(modal);
    });
});

document.querySelectorAll(".modal-backdrop").forEach((modal) => {
    modal.addEventListener("click", (event) => {
        if (event.target === modal) {
            closeModal(modal);
        }
    });
});

document.querySelectorAll(".suggestion").forEach((button) => {
    button.addEventListener("click", () => {
        elements.messageInput.value = button.textContent.trim();
        resizeInput();
        elements.messageInput.focus();
    });
});

async function bootstrap() {
    await loadHealth();

    try {
        await loadProjects();
        await loadConversations();
    } catch (error) {
        showError(error.message);
    }

    newConversation();
}

bootstrap();
