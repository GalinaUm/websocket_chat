import './style.css'

const app = document.querySelector<HTMLDivElement>('#app')!

let token: string | null = null
let ws: WebSocket | null = null
let currentRoomId: number | null = null

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
}

async function showRooms() {
    app.innerHTML = `
    <div class="rooms">
      <h2>Комнаты</h2>
      <form id="room-form"><input id="room-name" placeholder="Название" /><button>Создать</button></form>
      <ul id="room-list"></ul>
    </div>
    `
    document.querySelector('#room-form')!.addEventListener('submit', async (e) => {
        e.preventDefault()
        const name = (document.querySelector('#room-name') as HTMLInputElement).value
        await api('/rooms', { method: 'POST', body: JSON.stringify({ name }) })
        await showRooms()
    })

    const res = await api('/rooms')
    const rooms = (await res.json()) as { id: number; name: string }[]
    const list = document.querySelector('#room-list')!
    rooms.forEach((room) => {
        const li = document.createElement('li')
        li.textContent = room.name
        li.style.cursor = 'pointer'
        li.addEventListener('click', () => openChat(room.id))
        list.appendChild(li)
    })
}

function openChat(roomId: number) {
    currentRoomId = roomId
    app.innerHTML = `
      <div class="chat">
        <h2>Комната ${roomId}</h2>
        <div id="messages"></div>
        <form id="message-form"><input id="msg" placeholder="Сообщение" required /><button>Отправить</button></form>
      </div>
    `
    document.querySelector('#message-form')!.addEventListener('submit', async (e) => {
        e.preventDefault()
        const content = (document.querySelector('#msg') as HTMLInputElement).value
        const input = document.querySelector('#msg') as HTMLInputElement
        input.value = ''
        await api(`/rooms/${roomId}/messages`, { method: 'POST', body: JSON.stringify({ content }) })
    })

    ws = new WebSocket(`ws://${location.host}/ws/rooms/${roomId}?token=${token}`)
    ws.onmessage = (event) => {
        const data = JSON.parse(event.data)
        const box = document.querySelector('#messages')!
        const div = document.createElement('div')
        div.textContent = `${data.username}: ${data.content}`
        box.appendChild(div)
    }
}

showLogin()
