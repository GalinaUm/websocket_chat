import './style.css'

const app = document.querySelector<HTMLDivElement>('#app')!

let token: string | null = null
let ws: WebSocket | null = null
let currentUserId: number | null = null
let roomCreatorId: number | null = null
let myRoomIds = new Set<number>()
let pendingRequests = new Set<number>()
let typingHintTimer: number | null = null

async function api(path: string, options: RequestInit = {}): Promise<Response> {
    const headers: Record<string, string> = { 'Content-Type': 'application/json' }
    if (token) headers['Authorization'] = `Bearer ${token}`
    return fetch(path, { ...options, headers })
}

function showLogin() {
    app.innerHTML = `
        <form id="login-form">
            <h2>Вход</h2>
            <input id="username" placeholder="Логин" required />
            <input id="password" type="password" placeholder="Пароль" required />
            <button type="submit">Войти</button>
            <p id="error"></p>
        </form>
        <form id="register-form">
            <h2>Регистрация</h2>
            <input id="reg-email" type="email" placeholder="Email" required />
            <input id="reg-username" placeholder="Логин" required />
            <input id="reg-password" type="password" placeholder="Пароль" required />
            <button type="submit">Зарегистрироваться</button>
            <p id="reg-error" class="error"></p>
        </form>
    `
    document.querySelector('#login-form')!.addEventListener('submit', async (e) => {
        e.preventDefault()
        const username = (document.querySelector('#username') as HTMLInputElement).value
        const password = (document.querySelector('#password') as HTMLInputElement).value
        try {
            const res = await fetch('/auth/login', {
                method: 'POST',
                headers: { 'Content-Type': 'application/x-www-form-urlencoded'},
                body: new URLSearchParams({ username, password}),
            })
            if (!res.ok) throw new Error('Неверный логин или пароль')
            token = ((await res.json()) as { access_token: string }).access_token
            await showRooms()
        } catch (err) {
            ;(document.querySelector('#error') as HTMLParagraphElement).textContent =
              (err as Error).message
        }
    })

    document.querySelector('#register-form')!.addEventListener('submit', async (e) => {
        e.preventDefault()
        const errEl = document.querySelector('#reg-error') as HTMLParagraphElement
        errEl.textContent = ''
        try {
            const res = await fetch('/auth/register', {
                method: 'POST',
                headers: { 'Content-Type': 'application/json' },
                body: JSON.stringify({
                    email: (document.querySelector('#reg-email') as HTMLInputElement).value,
                    username: (document.querySelector('#reg-username') as HTMLInputElement).value,
                    password: (document.querySelector('#reg-password') as HTMLInputElement).value,
                }),
            })
            if (!res.ok) {
                const data = await res.json().catch(() => ({}))
                throw new Error((data as { detail?: string }).detail ?? 'Не удалось зарегистрироваться')
            }
            const hint = document.querySelector('#error') as HTMLParagraphElement
            hint.textContent = 'Регистрация успешна — войдите с новым логином'
            hint.style.color = '#a6e3a1'
            ;(document.querySelector('#register-form') as HTMLFormElement).hidden = true
        } catch (err) {
            errEl.textContent = (err as Error).message
        }
    })
}

async function showRooms() {
    app.innerHTML = `
    <div class="rooms">
    <p id="me"></p>
    <button id="btn-logout">Выйти</button>
      <h2>Комнаты</h2>
      <p id="stats">Мои комнаты: <span id="my-rooms-count">…</span> из <span id="max-rooms">20</span> · всего комнат: <span id="total-rooms">…</span></p>
      <p id="room-error" class="error"></p>
      <form id="room-form"><input id="room-name" placeholder="Название" /><button>Создать</button></form>
      <ul id="room-list"></ul>
      <h3>Пользователи</h3>
      <form id="user-search-form"><input id="user-search" placeholder="Поиск по имени" /><button type="submit">Найти</button></form>
      <ul id="user-list"></ul>
    </div>
    `

    document.querySelector('#btn-logout')!.addEventListener('click', () => {
        if (ws) { ws.close(); ws = null }
        token = null
        currentUserId = null
        roomCreatorId = null
        myRoomIds.clear()
        pendingRequests.clear()
        showLogin()
    })

    const meRes = await api('/auth/me')
    if (meRes.ok) {
        const me = (await meRes.json()) as { id: number; username: string }
        currentUserId = me.id
        ;(document.querySelector('#me') as HTMLParagraphElement).textContent = `Привет, ${me.username}!`
    }

    const mineRes = await api('/rooms/mine')
    if (mineRes.ok) {
        const mine = (await mineRes.json()) as number[]
        myRoomIds = new Set(mine)
    }

    const unreadRes = await api('/rooms/unread')
    let unreadCounts = new Map<number, number>()
    if (unreadRes.ok) {
        const items = (await unreadRes.json()) as { room_id: number; unread: number }[]
        unreadCounts = new Map(items.map((i) => [i.room_id, i.unread]))
    }

    let stats: { my_rooms: number; max_rooms_per_user: number; total_rooms: number } | null = null
    const statsRes = await api('/rooms/stats')
    if (statsRes.ok) {
        const st = (await statsRes.json()) as { my_rooms: number; max_rooms_per_user: number; total_rooms: number }
        stats = st
        ;(document.querySelector('#my-rooms-count') as HTMLSpanElement).textContent = String(st.my_rooms)
        ;(document.querySelector('#max-rooms') as HTMLSpanElement).textContent = String(st.max_rooms_per_user)
        ;(document.querySelector('#total-rooms') as HTMLSpanElement).textContent = String(st.total_rooms)
    }

    document.querySelector('#room-form')!.addEventListener('submit', async (e) => {
        e.preventDefault()
        const errorEl = document.querySelector('#room-error') as HTMLParagraphElement
        errorEl.textContent = ''
        const name = (document.querySelector('#room-name') as HTMLInputElement).value
        if (stats && stats.my_rooms >= stats.max_rooms_per_user) {
            errorEl.textContent = `Лимит: можно создать не больше ${stats.max_rooms_per_user} комнат`
            return
        }
        const resp = await api('/rooms', { method: 'POST', body: JSON.stringify({ name }) })
        if (!resp.ok) {
            const data = await resp.json().catch(() => ({}))
            errorEl.textContent = (data as { detail?: string }).detail ?? 'Не удалось создать комнату'
            return
        }
        await showRooms()
    })

    const searchForm = document.querySelector('#user-search-form')!
    const searchInput = document.querySelector('#user-search') as HTMLInputElement
    const runSearch = async () => {
        const q = searchInput.value.trim()
        const res = await api(`/users?q=${encodeURIComponent(q)}`)
        const users = (await res.json()) as { id: number; username: string }[]
        const list = document.querySelector('#user-list')!
        list.innerHTML = ''
        users.forEach((u) => {
            const li = document.createElement('li')
            li.textContent = u.username
            list.appendChild(li)
        })
    }
    searchForm.addEventListener('submit', (e) => { e.preventDefault(); runSearch() })

    const res = await api('/rooms')
    const rooms = (await res.json()) as { id: number; name: string; created_by: number }[]
    const list = document.querySelector('#room-list')!
    rooms.forEach((room) => {
        if (room.created_by === currentUserId) myRoomIds.add(room.id)
        const li = document.createElement('li')
        const nameSpan = document.createElement('span')
        nameSpan.textContent = room.name
        const unread = unreadCounts.get(room.id)
        if (unread) {
            const ub = document.createElement('span')
            ub.className = 'unread-badge'
            ub.textContent = String(unread)
            nameSpan.appendChild(ub)
        }
        if (room.created_by === currentUserId) {
            const badge = document.createElement('span')
            badge.className = 'badge'
            badge.textContent = '· создатель'
            nameSpan.appendChild(badge)
        }
        li.appendChild(nameSpan)

        const btn = document.createElement('button')
        if (myRoomIds.has(room.id)) {
            btn.textContent = 'Открыть'
            btn.addEventListener('click', (e) => { e.stopPropagation(); openChat(room.id) })
        } else if (pendingRequests.has(room.id)) {
            btn.textContent = 'Заявка отправлена'
            btn.disabled = true
        } else {
            btn.textContent = 'Подать заявку'
            btn.addEventListener('click', (e) => {
                e.stopPropagation()
                knock(room.id)
            })
        }
        li.appendChild(btn)
        li.addEventListener('click', () => openChat(room.id))
        list.appendChild(li)
    })
}

async function knock(roomId: number) {
    const errEl = document.querySelector('#room-error') as HTMLParagraphElement
    errEl.textContent = ''
    const res = await api(`/rooms/${roomId}/request`, { method: 'POST' })
    const data = (await res.json().catch(() => ({}))) as { detail?: string }
    if (res.ok) {
        pendingRequests.add(roomId)
    } else {
        const detail = data.detail ?? 'Не удалось отправить заявку'
        if (detail === 'Already a member') {
            myRoomIds.add(roomId)
        } else if (detail === 'Request already sent') {
            pendingRequests.add(roomId)
        } else {
            errEl.textContent = detail
        }
    }
    await showRooms()
}

function openChat(roomId: number) {
    app.innerHTML = `
      <div class="chat">
        <div class="chat-header">
          <h2>Комната ${roomId}</h2>
          <span id="online-count"></span>
          <button id="btn-back">← На главную</button>
          <button id="btn-leave">Покинуть</button>
          <button id="btn-delete-room">Удалить</button>
        </div>
        <div id="requests" hidden>
          <h3>Заявки на вступление</h3>
          <ul id="request-list"></ul>
        </div>
        <div id="invite" hidden>
          <h3>Пригласить по имени</h3>
          <form id="invite-form"><input id="invite-username" placeholder="Имя пользователя" /><button>Пригласить</button></form>
          <p id="invite-error" class="error"></p>
        </div>
        <div class="chat-body">
          <div id="messages"></div>
          <aside id="members">
            <h3>Участники</h3>
            <ul id="member-list"></ul>
          </aside>
        </div>
        <form id="message-form"><input id="msg" placeholder="Сообщение" required /><button>Отправить</button></form>
        <p id="typing-hint"></p>
      </div>
    `
    document.querySelector('#btn-back')!.addEventListener('click', () => {
        leaveChat()
        showRooms()
    })

    document.querySelector('#btn-leave')!.addEventListener('click', () => {
        ws!.send(JSON.stringify({ type: 'leave_room' }))
        myRoomIds.delete(roomId)
        setTimeout(() => { leaveChat(); showRooms() }, 300)
    })

    document.querySelector('#btn-delete-room')!.addEventListener('click', () => {
        ws!.send(JSON.stringify({ type: 'delete_room' }))
        setTimeout(() => { leaveChat(); showRooms() }, 300)
        })

    ws = new WebSocket(`ws://${location.host}/ws/rooms/${roomId}?token=${token}`)

    ws.onopen = () => {
        ws!.send(JSON.stringify({ type: 'get_messages' }))
        ws!.send(JSON.stringify({ type: 'get_members' }))
    }

    ws.onmessage = (event) => {
        const data = JSON.parse(event.data)
        if (data.type === 'welcome') {
            currentUserId = data.my_id
            roomCreatorId = data.room.created_by
            myRoomIds.add(roomId)
            if (currentUserId === roomCreatorId) {
                const panel = document.querySelector('#requests') as HTMLElement | null
                if (panel) panel.hidden = false
                const invite = document.querySelector('#invite') as HTMLElement | null
                if (invite) invite.hidden = false
                ws!.send(JSON.stringify({ type: 'get_requests' }))
            }
        } else if (data.type === 'history') {
            renderMessages(data.messages)
        } else if (data.type === 'new_message') {
            appendMessage(data)
        } else if (data.type === 'error') {
            console.error(data.detail)
        } else if (data.type === 'members') {
            renderMembers(data.members)
        } else if (data.type === 'requests') {
            renderRequests(data.requests)
        } else if (data.type === 'request_resolved') {
            ws!.send(JSON.stringify({ type: 'get_requests' }))
            ws!.send(JSON.stringify({ type: 'get_members' }))
        } else if (data.type === 'member_joined') {
            appendSystemMessage(`→ ${data.username} присоединился`)
            ws!.send(JSON.stringify({ type: 'get_members' }))
        } else if (data.type === 'member_left') {
            appendSystemMessage(`← ${data.username} покинул комнату`)
            ws!.send(JSON.stringify({ type: 'get_members' }))
        } else if (data.type === 'typing') {
            if (data.user_id !== currentUserId) showTyping(data.username)
        } else if (data.type === 'message_edited') {
            const el = document.querySelector(`[data-message-id="${data.id}"] .msg-text`)
            if (el) el.textContent = `${data.username}: ${data.content}`
        } else if (data.type === 'message_deleted') {
            document.querySelector(`[data-message-id="${data.id}"]`)?.remove()
        } else if (data.type === 'room_deleted') {
            leaveChat()
            showRooms()
        }
    }

    ws.onclose = (event) => {
        if (event.code === 1008) {
            const box = document.querySelector('#messages')
            if (box) box.innerHTML = '<p class="error">Вы не участник комнаты — вернитесь на главную и подайте заявку</p>'
        }
    }

    document.querySelector('#message-form')!.addEventListener('submit', async (e) => {
        e.preventDefault()
        const input = document.querySelector('#msg') as HTMLInputElement
        const content = input.value
        input.value = ''
        ws!.send(JSON.stringify({ type: 'send_message', content }))
    })

    const msgInput = document.querySelector('#msg') as HTMLInputElement
    let typingTimer: number | undefined
    msgInput.addEventListener('input', () => {
        window.clearTimeout(typingTimer)
        typingTimer = window.setTimeout(() => {
            ws!.send(JSON.stringify({ type: 'typing' }))
        }, 400)
    })

    document.querySelector('#invite-form')!.addEventListener('submit', async (e) => {
        e.preventDefault()
        const errEl = document.querySelector('#invite-error') as HTMLParagraphElement
        errEl.textContent = ''
        const username = (document.querySelector('#invite-username') as HTMLInputElement).value
        const res = await api(`/rooms/${roomId}/invite`, {
            method: 'POST',
            body: JSON.stringify({ username }),
        })
        if (!res.ok) {
            const data = await res.json().catch(() => ({}))
            errEl.textContent = (data as { detail?: string }).detail ?? 'Не удалось пригласить'
            return
        }
        ;(document.querySelector('#invite-username') as HTMLInputElement).value = ''
        ws!.send(JSON.stringify({ type: 'get_members' }))
    })
}

function leaveChat() {
    if (ws) {
        ws.onmessage = null
        ws.close()
        ws = null
    }
}

function appendMessage(m: { id: number; username?: string; user_id?: number; content: string }) {
    const box = document.querySelector('#messages')!
    const div = document.createElement('div')
    div.dataset.messageId = String(m.id)

    const label = document.createElement('span')
    label.className = 'msg-text'
    label.textContent = `${m.username ?? `user${m.user_id}`}: ${m.content}`
    div.appendChild(label)

    const canDelete = m.user_id === currentUserId || roomCreatorId === currentUserId
    if (canDelete) {
        const del = document.createElement('button')
        del.className = 'msg-btn'
        del.textContent = '🗑'
        del.addEventListener('click', () => {
            ws!.send(JSON.stringify({ type: 'delete_message', message_id: m.id}))
        })
        div.appendChild(del)
    }

    if (m.user_id === currentUserId) {
        const edit = document.createElement('button')
        edit.className = 'msg-btn'
        edit.textContent = '✎'
        edit.addEventListener('click', () => {
            const input = document.createElement('input')
            input.value = m.content
            div.replaceChild(input, label)
            input.focus()
            const finish = () => {
                const value = input.value.trim()
                if (value && value !== m.content) {
                    ws!.send(JSON.stringify({ type: 'edit_message', message_id: m.id, content: value }))
                    label.textContent = `${m.username ?? `user${m.user_id}`}: ${value}`
                }
                div.replaceChild(label, input)
            }
            input.addEventListener('blur', finish)
            input.addEventListener('keydown', (e) => {
                if (e.key === 'Enter' || e.key === 'Escape') input.blur()
            })
        })
        div.appendChild(edit)
    }
    box.appendChild(div)
}

function showTyping(username: string) {
    const hint = document.querySelector('#typing-hint')
    if (!hint) return
    hint.textContent = `${username} печатает…`
    if (typingHintTimer !== null) window.clearTimeout(typingHintTimer)
    typingHintTimer = window.setTimeout(() => { hint.textContent = '' }, 2000)
}


function renderMessages(messages: { id: number; username?: string; user_id?: number; content: string }[]) {
    const box = document.querySelector('#messages')!
    box.innerHTML = ''
    messages.forEach(appendMessage)
}

function renderMembers(members: { id: number; username: string; online: boolean }[]) {
    const list = document.querySelector('#member-list')!
    list.innerHTML = ''
    const counter = document.querySelector('#online-count')
    if (counter) counter.textContent = `🟢 ${members.filter((m) => m.online).length} из ${members.length} онлайн`
    members.forEach((m) => {
        const li = document.createElement('li')
        li.textContent = `${m.online ? '🟢' : '⚪'} ${m.username}`
list.appendChild(li)
    })
}

function appendSystemMessage(text: string) {
    const box = document.querySelector('#messages')
    if (!box) return
    const div = document.createElement('div')
    div.className = 'system'
    div.textContent = text
    box.appendChild(div)
}

function renderRequests(requests: { id: number; username: string }[]) {
    const list = document.querySelector('#request-list')
    if (!list) return
    list.innerHTML = ''
    requests.forEach((r) => {
        const li = document.createElement('li')
        li.textContent = r.username
        const accept = document.createElement('button')
        accept.textContent = 'Принять'
        accept.addEventListener('click', () => {
            ws!.send(JSON.stringify({ type: 'approve_request', request_id: r.id }))
        })
        const reject = document.createElement('button')
        reject.textContent = 'Отклонить'
        reject.addEventListener('click', () => {
            ws!.send(JSON.stringify({ type: 'reject_request', request_id: r.id }))
        })
        li.appendChild(accept)
        li.appendChild(reject)
        list.appendChild(li)
    })
}

showLogin()
