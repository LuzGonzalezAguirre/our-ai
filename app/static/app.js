const state = {
    conversationId: null,
    conversations: [],
    projects: [],
    projectId: null,
    knowledge: [],
    sending: false,
    confirmResolver: null,
};

const elements = {
    conversationList: document.getElementById("conversationList"),
    conversationCount: document.getElementById("conversationCount"),
    newChatButton: document.getElementById("newChatButton"),
    deleteChatButton: document.getElementById("deleteChatButton"),
    conversationTitle: document.getElementById("conversationTitle"),
    conversationMeta: document.getElementById("conversationMeta"),
    messages: document.getElementById("messages"),
    emptyState: document.getElementById("emptyState"),
    chatForm: document.getElementById("chatForm"),
    messageInput: document.getElementById("messageInput"),
    sendButton: document.getElementById("sendButton"),
    modelBadge: document.getElementById("modelBadge"),
    ragBadge: document.getElementById("ragBadge"),
    integrationBadge: document.getElementById("integrationBadge"),
    composerSource: document.getElementById("composerSource"),
    statusDot: document.getElementById("statusDot"),
    statusDotSide: document.getElementById("statusDotSide"),
    statusText: document.getElementById("statusText"),
    statusTextSide: document.getElementById("statusTextSide"),
    statusDetail: document.getElementById("statusDetail"),
    projectSelect: document.getElementById("projectSelect"),
    projectEyebrow: document.getElementById("projectEyebrow"),
    newProjectButton: document.getElementById("newProjectButton"),
    projectNavButton: document.getElementById("projectNavButton"),
    knowledgeButton: document.getElementById("knowledgeButton"),
    knowledgeNavButton: document.getElementById("knowledgeNavButton"),
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
    knowledgeCount: document.getElementById("knowledgeCount"),
    knowledgeProjectTitle: document.getElementById("knowledgeProjectTitle"),
    knowledgeDetail: document.getElementById("knowledgeDetail"),
    knowledgeDetailTitle: document.getElementById("knowledgeDetailTitle"),
    knowledgeDetailMeta: document.getElementById("knowledgeDetailMeta"),
    knowledgeDetailContent: document.getElementById("knowledgeDetailContent"),
    knowledgeDetailClose: document.getElementById("knowledgeDetailClose"),
    knowledgeChunkCount: document.getElementById("knowledgeChunkCount"),
    knowledgeChunkList: document.getElementById("knowledgeChunkList"),
    sidebar: document.getElementById("sidebar"),
    sidebarToggle: document.getElementById("sidebarToggle"),
    sidebarClose: document.getElementById("sidebarClose"),
    sidebarBackdrop: document.getElementById("sidebarBackdrop"),
    confirmModal: document.getElementById("confirmModal"),
    confirmTitle: document.getElementById("confirmTitle"),
    confirmMessage: document.getElementById("confirmMessage"),
    confirmCancel: document.getElementById("confirmCancel"),
    confirmAccept: document.getElementById("confirmAccept"),
    toastRegion: document.getElementById("toastRegion"),
};

function setEmptyState(visible) {
    elements.emptyState.hidden = !visible;
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
    const projectName = project?.name || "General";

    elements.projectEyebrow.textContent = projectName.toUpperCase();
    elements.composerSource.textContent =
        "Qwen local · " + projectName;
}

function setStatus(mode, title, detail) {
    const className =
        mode === "online"
            ? "status-dot online"
            : mode === "degraded"
                ? "status-dot degraded"
                : "status-dot";

    elements.statusDot.className = className;
    elements.statusDotSide.className = className;
    elements.statusText.textContent = title;
    elements.statusTextSide.textContent = title;
    elements.statusDetail.textContent = detail;
}

function notify(message, type = "info") {
    const toast = document.createElement("div");
    toast.className = "toast " + type;
    toast.textContent = message;
    elements.toastRegion.appendChild(toast);

    window.setTimeout(() => {
        toast.remove();
    }, 4200);
}

function openSidebar() {
    elements.sidebar.classList.add("open");
    elements.sidebarBackdrop.hidden = false;
    elements.sidebarToggle.setAttribute("aria-expanded", "true");
}

function closeSidebar() {
    elements.sidebar.classList.remove("open");
    elements.sidebarBackdrop.hidden = true;
    elements.sidebarToggle.setAttribute("aria-expanded", "false");
}

function openModal(modal) {
    modal.hidden = false;
    document.body.classList.add("modal-open");
}

function closeModal(modal) {
    modal.hidden = true;

    if (
        elements.projectModal.hidden &&
        elements.knowledgeModal.hidden &&
        elements.confirmModal.hidden
    ) {
        document.body.classList.remove("modal-open");
    }
}

function confirmAction({
    title = "Confirmar",
    message = "¿Deseas continuar?",
    acceptText = "Eliminar",
} = {}) {
    elements.confirmTitle.textContent = title;
    elements.confirmMessage.textContent = message;
    elements.confirmAccept.textContent = acceptText;
    openModal(elements.confirmModal);

    return new Promise((resolve) => {
        state.confirmResolver = resolve;
        elements.confirmCancel.focus();
    });
}

function resolveConfirmation(value) {
    if (state.confirmResolver) {
        state.confirmResolver(value);
        state.confirmResolver = null;
    }

    closeModal(elements.confirmModal);
}

function escapeHtml(value) {
    return String(value ?? "")
        .replaceAll("&", "&amp;")
        .replaceAll("<", "&lt;")
        .replaceAll(">", "&gt;")
        .replaceAll('"', "&quot;")
        .replaceAll("'", "&#039;");
}

function normalizeAssistantMarkdown(value) {
    return String(value ?? "")
        .replace(/\\\\([#*_-])/g, "$1")
        .replace(/\\\\(\d+\\.)/g, "$1")
        .replace(/\\\\$/gm, "")
        .replace(/[ \t]+$/gm, "");
}

function renderInline(value) {
    let html = escapeHtml(value);
    const inlineCodePattern = new RegExp(
        String.fromCharCode(96) +
        "([^" + String.fromCharCode(96) + "]+)" +
        String.fromCharCode(96),
        "g"
    );

    html = html.replace(
        /\*\*([^*]+)\*\*/g,
        "<strong>$1</strong>"
    );

    html = html.replace(
        inlineCodePattern,
        "<code>$1</code>"
    );

    return html;
}

function appendTextLine(container, line) {
    const trimmed = line.trim();

    if (!trimmed) {
        return;
    }

    const headingMatch = trimmed.match(/^(#{1,4})\s+(.+)$/);

    if (headingMatch) {
        const heading = document.createElement(
            headingMatch[1].length <= 2 ? "h3" : "h4"
        );
        heading.innerHTML = renderInline(headingMatch[2]);
        container.appendChild(heading);
        return;
    }

    const paragraph = document.createElement("p");
    paragraph.innerHTML = renderInline(trimmed);
    container.appendChild(paragraph);
}

function appendTextBlock(container, block) {
    const trimmed = block.trim();

    if (!trimmed) {
        return;
    }

    const lines = trimmed.split("\n");
    let list = null;
    let listType = null;

    const flushList = () => {
        if (list) {
            container.appendChild(list);
            list = null;
            listType = null;
        }
    };

    for (const rawLine of lines) {
        const line = rawLine.trim();

        if (!line) {
            flushList();
            continue;
        }

        const bulletMatch = line.match(/^[-*]\s+(.+)$/);
        const orderedMatch = line.match(/^\d+\.\s+(.+)$/);

        if (bulletMatch) {
            if (listType !== "ul") {
                flushList();
                list = document.createElement("ul");
                listType = "ul";
            }

            const item = document.createElement("li");
            item.innerHTML = renderInline(bulletMatch[1]);
            list.appendChild(item);
            continue;
        }

        if (orderedMatch) {
            if (listType !== "ol") {
                flushList();
                list = document.createElement("ol");
                listType = "ol";
            }

            const item = document.createElement("li");
            item.innerHTML = renderInline(orderedMatch[1]);
            list.appendChild(item);
            continue;
        }

        flushList();
        appendTextLine(container, line);
    }

    flushList();
}

function renderAssistantContent(container, content) {
    const normalized = normalizeAssistantMarkdown(content);
    const fence = String.fromCharCode(96).repeat(3);
    const segments = normalized.split(fence);

    segments.forEach((segment, index) => {
        if (index % 2 === 1) {
            const code = document.createElement("pre");
            const codeInner = document.createElement("code");
            const lines = segment.replace(/^\n/, "").split("\n");

            if (
                lines.length > 1 &&
                /^[a-zA-Z0-9_+#.-]+$/.test(lines[0].trim())
            ) {
                lines.shift();
            }

            codeInner.textContent = lines.join("\n").trimEnd();
            code.appendChild(codeInner);
            container.appendChild(code);
            return;
        }

        const blocks = segment.split(/\n\s*\n/);

        for (const block of blocks) {
            appendTextBlock(container, block);
        }
    });
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
    } else if (role === "assistant") {
        renderAssistantContent(messageContent, content);
    } else {
        messageContent.textContent = String(content ?? "");
        messageContent.style.whiteSpace = "pre-wrap";
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
    elements.conversationCount.textContent =
        String(state.conversations.length);

    if (state.conversations.length === 0) {
        const empty = document.createElement("div");
        empty.className = "conversation-empty";
        empty.textContent =
            "Todavía no hay conversaciones en este proyecto.";
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

        button.addEventListener("click", async () => {
            await loadConversation(conversation.id);
            closeSidebar();
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

function clearKnowledgeDetail() {
    elements.knowledgeDetail.hidden = true;
    elements.knowledgeDetailTitle.textContent = "Fuente";
    elements.knowledgeDetailMeta.textContent = "";
    elements.knowledgeDetailContent.textContent = "";
    elements.knowledgeChunkCount.textContent = "0";
    elements.knowledgeChunkList.replaceChildren();
}

async function loadKnowledgeDetail(source) {
    try {
        const detail = await requestJson(
            "/v1/projects/" +
                encodeURIComponent(state.projectId) +
                "/knowledge/" +
                encodeURIComponent(source.id)
        );

        elements.knowledgeDetailTitle.textContent =
            detail.title;
        elements.knowledgeDetailMeta.textContent =
            detail.chunk_count +
            (detail.chunk_count === 1
                ? " fragmento RAG"
                : " fragmentos RAG");
        elements.knowledgeDetailContent.textContent =
            detail.content;
        elements.knowledgeChunkCount.textContent =
            String(detail.chunk_count);
        elements.knowledgeChunkList.replaceChildren();

        for (const chunk of detail.chunks) {
            const item = document.createElement("div");
            item.className = "knowledge-chunk";

            const label = document.createElement("strong");
            label.textContent =
                "Fragmento " + (chunk.index + 1);

            const text = document.createElement("p");
            text.textContent = chunk.content;

            item.append(label, text);
            elements.knowledgeChunkList.appendChild(item);
        }

        elements.knowledgeDetail.hidden = false;
        elements.knowledgeDetail.scrollIntoView({
            behavior: "smooth",
            block: "nearest",
        });
    } catch (error) {
        notify(error.message, "error");
    }
}

function renderKnowledge() {
    elements.knowledgeList.replaceChildren();
    elements.knowledgeCount.textContent =
        String(state.knowledge.length);
    clearKnowledgeDetail();

    if (state.knowledge.length === 0) {
        const empty = document.createElement("div");
        empty.className = "knowledge-empty";
        empty.textContent =
            "Este proyecto todavía no tiene fuentes de conocimiento.";
        elements.knowledgeList.appendChild(empty);
        return;
    }

    for (const source of state.knowledge) {
        const row = document.createElement("div");
        row.className = "knowledge-item";

        const info = document.createElement("div");

        const title = document.createElement("strong");
        title.textContent = source.title;
        title.title = source.title;

        const meta = document.createElement("span");
        meta.textContent =
            source.chunk_count +
            (source.chunk_count === 1
                ? " fragmento"
                : " fragmentos");

        info.append(title, meta);

        const actions = document.createElement("div");
        actions.className = "knowledge-item-actions";

        const view = document.createElement("button");
        view.type = "button";
        view.className = "knowledge-view";
        view.textContent = "Ver";
        view.addEventListener("click", () => {
            loadKnowledgeDetail(source);
        });

        const remove = document.createElement("button");
        remove.type = "button";
        remove.className = "knowledge-delete";
        remove.textContent = "×";
        remove.title = "Eliminar fuente";
        remove.setAttribute(
            "aria-label",
            "Eliminar " + source.title
        );

        remove.addEventListener("click", async () => {
            const confirmed = await confirmAction({
                title: "Eliminar fuente",
                message:
                    "Se eliminará “" +
                    source.title +
                    "” y sus fragmentos del proyecto.",
                acceptText: "Eliminar",
            });

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
                notify("Fuente eliminada.", "success");
            } catch (error) {
                notify(error.message, "error");
            }
        });

        actions.append(view, remove);
        row.append(info, actions);
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

        elements.modelBadge.textContent =
            health.model || "Modelo local";

        if (health.action_tracker === "configured") {
            elements.integrationBadge.textContent =
                "Action Tracker listo";
            elements.integrationBadge.className =
                "status-chip live";
        } else {
            elements.integrationBadge.textContent =
                "Action Tracker off";
            elements.integrationBadge.className =
                "status-chip neutral";
        }

        if (health.database === "connected") {
            setStatus(
                "online",
                "Sistema listo",
                health.action_tracker === "configured"
                    ? "PostgreSQL + Action Tracker"
                    : "PostgreSQL conectado"
            );
        } else {
            setStatus(
                "degraded",
                "Configuración pendiente",
                "PostgreSQL desconectado"
            );
        }
    } catch {
        setStatus(
            "degraded",
            "Servidor no disponible",
            "Revisa FastAPI"
        );
        elements.integrationBadge.textContent =
            "Action Tracker";
        elements.integrationBadge.className =
            "status-chip neutral";
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
    } catch (error) {
        state.conversations = [];
        renderConversationList();
        notify(
            "No se pudieron cargar las conversaciones: " +
                error.message,
            "error"
        );
    }
}

async function loadKnowledge() {
    if (!state.projectId) {
        state.knowledge = [];
        renderKnowledge();
        return;
    }

    clearKnowledgeDetail();

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
        elements.conversationMeta.textContent =
            "Historial guardado · Proyecto " +
            (currentProject()?.name || "General");
        elements.deleteChatButton.disabled = false;

        elements.ragBadge.textContent = "Contexto guardado";
        elements.ragBadge.className = "context-badge";

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
    elements.conversationTitle.textContent =
        "Nueva conversación";
    elements.conversationMeta.textContent =
        "Asistente local · Solo lectura en Action Tracker";
    elements.deleteChatButton.disabled = true;
    elements.ragBadge.textContent = "RAG local";
    elements.ragBadge.className = "context-badge";
    renderMessages([]);
    renderConversationList();
    closeSidebar();
    elements.messageInput.focus();
}

function showError(message) {
    setEmptyState(false);

    const node = createMessageElement(
        "assistant",
        "No se pudo completar la solicitud. " + message
    );
    elements.messages.appendChild(node);
    scrollToBottom();
    notify(message, "error");
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

        if (result.action_tracker_used) {
            elements.ragBadge.textContent =
                "Action Tracker live";
            elements.ragBadge.className =
                "context-badge live";
        } else if (result.knowledge_chunks_used > 0) {
            elements.ragBadge.textContent =
                result.knowledge_chunks_used + " chunks";
            elements.ragBadge.className =
                "context-badge";
        } else {
            elements.ragBadge.textContent = "Chat local";
            elements.ragBadge.className =
                "context-badge";
        }

        elements.deleteChatButton.disabled = false;

        await loadConversations();

        const active = state.conversations.find(
            (item) => item.id === state.conversationId
        );

        elements.conversationTitle.textContent =
            active?.title || "Conversación";
        elements.conversationMeta.textContent =
            result.action_tracker_used
                ? "Respuesta con datos live de Action Tracker"
                : "Historial guardado · Proyecto " +
                    (currentProject()?.name || "General");

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

    const confirmed = await confirmAction({
        title: "Eliminar conversación",
        message:
            "Se eliminará esta conversación y todos sus mensajes guardados.",
        acceptText: "Eliminar conversación",
    });

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
        notify("Conversación eliminada.", "success");
    } catch (error) {
        notify(error.message, "error");
    }
}

function resizeInput() {
    elements.messageInput.style.height = "auto";
    elements.messageInput.style.height =
        Math.min(
            Math.max(elements.messageInput.scrollHeight, 38),
            170
        ) + "px";
}

async function openKnowledge() {
    const project = currentProject();

    elements.knowledgeProjectTitle.textContent =
        project
            ? "Conocimiento · " + project.name
            : "Conocimiento";

    try {
        await loadKnowledge();
        openModal(elements.knowledgeModal);
        elements.knowledgeTitle.focus();
    } catch (error) {
        notify(error.message, "error");
    }
}

function openProjectModal() {
    elements.projectForm.reset();
    openModal(elements.projectModal);
    elements.projectName.focus();
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

elements.projectSelect.addEventListener(
    "change",
    async () => {
        state.projectId = elements.projectSelect.value;
        updateProjectHeader();
        newConversation();
        await loadConversations();
    }
);

elements.newProjectButton.addEventListener(
    "click",
    openProjectModal
);

elements.projectNavButton.addEventListener(
    "click",
    openProjectModal
);

elements.knowledgeButton.addEventListener(
    "click",
    openKnowledge
);

elements.knowledgeNavButton.addEventListener(
    "click",
    openKnowledge
);

elements.knowledgeDetailClose.addEventListener(
    "click",
    clearKnowledgeDetail
);

document
    .querySelectorAll("[data-nav-chat]")
    .forEach((button) => {
        button.addEventListener("click", () => {
            closeSidebar();
            elements.messageInput.focus();
        });
    });

elements.projectForm.addEventListener(
    "submit",
    async (event) => {
        event.preventDefault();

        const submit =
            elements.projectForm.querySelector(
                'button[type="submit"]'
            );
        submit.disabled = true;

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
            notify(
                "Proyecto “" +
                    project.name +
                    "” creado.",
                "success"
            );
        } catch (error) {
            notify(error.message, "error");
        } finally {
            submit.disabled = false;
        }
    }
);

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
                        title:
                            elements.knowledgeTitle.value.trim(),
                        content:
                            elements.knowledgeContent.value.trim(),
                    }),
                }
            );

            elements.knowledgeForm.reset();
            await loadKnowledge();
            notify(
                "Conocimiento agregado al proyecto.",
                "success"
            );
        } catch (error) {
            notify(error.message, "error");
        } finally {
            elements.knowledgeSubmitButton.disabled = false;
            elements.knowledgeSubmitButton.textContent =
                originalText;
        }
    }
);

document
    .querySelectorAll("[data-close-modal]")
    .forEach((button) => {
        button.addEventListener("click", () => {
            const modal = document.getElementById(
                button.dataset.closeModal
            );
            closeModal(modal);
        });
    });

document
    .querySelectorAll(".modal-backdrop")
    .forEach((modal) => {
        modal.addEventListener("click", (event) => {
            if (event.target !== modal) {
                return;
            }

            if (modal === elements.confirmModal) {
                resolveConfirmation(false);
                return;
            }

            closeModal(modal);
        });
    });

elements.confirmCancel.addEventListener(
    "click",
    () => resolveConfirmation(false)
);

elements.confirmAccept.addEventListener(
    "click",
    () => resolveConfirmation(true)
);

elements.sidebarToggle.addEventListener(
    "click",
    openSidebar
);

elements.sidebarClose.addEventListener(
    "click",
    closeSidebar
);

elements.sidebarBackdrop.addEventListener(
    "click",
    closeSidebar
);

document
    .querySelectorAll(".suggestion")
    .forEach((button) => {
        button.addEventListener("click", () => {
            const strong = button.querySelector("strong");
            elements.messageInput.value =
                strong?.textContent.trim() ||
                button.textContent.trim();
            resizeInput();
            elements.messageInput.focus();
        });
    });

document.addEventListener("keydown", (event) => {
    if (event.key !== "Escape") {
        return;
    }

    if (!elements.confirmModal.hidden) {
        resolveConfirmation(false);
        return;
    }

    if (!elements.projectModal.hidden) {
        closeModal(elements.projectModal);
    }

    if (!elements.knowledgeModal.hidden) {
        closeModal(elements.knowledgeModal);
    }

    closeSidebar();
});

window.addEventListener("resize", () => {
    if (window.innerWidth > 900) {
        closeSidebar();
    }
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
    resizeInput();
}

bootstrap();
