import { useState, useEffect, useRef } from 'react'
import axios from 'axios'
import ReactMarkdown from 'react-markdown';

const ChatWindow = () => {
  const [problems, setProblems] = useState([])
  const [selectedProblem, setSelectedProblem] = useState('')
  const [userInput, setUserInput] = useState('')
  const [messages, setMessages] = useState([])
  const [sessionId, setSessionId] = useState(null)
  const [loading, setLoading] = useState(false)
  const [stage, setStage] = useState('selection') // 'selection' | 'chat' | 'conclusion'
  const messagesEndRef = useRef(null)
  const inputRef = useRef(null)

  const API_URL = import.meta.env.VITE_API_URL || 'http://103.93.130.146:8340'

  // Load problem list
  useEffect(() => {
    axios.get(`${API_URL}/problems`)
      .then(res => setProblems(res.data))
      .catch(() => appendMessage({ type: 'system', text: 'Error loading topics.' }))
  }, [])

  // Auto-scroll
  useEffect(() => {
    messagesEndRef.current?.scrollIntoView({ behavior: 'smooth' })
  }, [messages])

  // Focus input whenever we enter chat/conclusion
  useEffect(() => {
    if (stage !== 'selection') {
      inputRef.current?.focus()
    }
  }, [stage])

  const appendMessage = msg =>
    setMessages(prev => [...prev, msg])

  const reset = () => {
    setMessages([])
    setSessionId(null)
    setStage('selection')
    setSelectedProblem('')
    setUserInput('')
  }

  // Handles both start & subsequent messages
  const handleServerResponse = data => {
    // display the assistant's message
    appendMessage({
      type: 'system',
      text: data.message,
      messageType: data.message_type,   // for styling
      resources: data.resources || []   // optional resources array
    })

    // move to conclusion only if message_type==='conclusion'
    if (data.message_type === 'conclusion') {
      setStage('conclusion')
    } else {
      setStage('chat')
    }
  }

  // Start a new session
  const startAssessment = async () => {
    if (!selectedProblem && !userInput) return
    setLoading(true)
    // echo user's choice/text
    appendMessage({ type: 'user', text: selectedProblem ? `Selected: ${selectedProblem}` : userInput })

    try {
      const payload = selectedProblem
        ? { problem_id: selectedProblem }
        : { user_input: userInput }
      const res = await axios.post(`${API_URL}/start`, payload)
      setSessionId(res.data.session_id)
      handleServerResponse(res.data)
    } catch {
      appendMessage({ type: 'system', text: 'Failed to start.' })
    } finally {
      setLoading(false)
      setUserInput('')
      setSelectedProblem('')
    }
  }

  // Send the next message in an ongoing session
  const submitAnswer = async () => {
    if (!sessionId || !userInput) return
    setLoading(true)
    appendMessage({ type: 'user', text: userInput })

    try {
      const res = await axios.post(`${API_URL}/answer`, {
        session_id: sessionId,
        user_answer: userInput
      })
      handleServerResponse(res.data)
    } catch {
      appendMessage({ type: 'system', text: 'Error processing.' })
    } finally {
      setLoading(false)
      setUserInput('')
    }
  }

  const handleSubmit = e => {
    e.preventDefault()
    if (stage === 'selection') startAssessment()
    else if (stage === 'chat') submitAnswer()
  }

  // Choose button label
  const sendLabel = loading ? '...' : (stage === 'selection' ? 'Start' : 'Send')

  return (
    <div className="flex flex-col h-full w-full">
      <div className="flex-1 overflow-auto p-4">
        {messages.length === 0 ? (
          <div className="text-center text-gray-500">
            Select a topic or describe your situation.
          </div>
        ) : (
          messages.map((msg, i) => {
            // Determine bubble color
            const bubbleClass = msg.type === 'user'
              ? 'bg-blue-500 text-white'
              : msg.messageType === 'urgent'
                ? 'bg-red-200 text-red-800'
                : msg.messageType === 'suggestion'
                  ? 'bg-green-200 text-green-800'
                  : msg.messageType === 'conclusion'
                    ? 'bg-purple-200 text-purple-800'
                    : 'bg-gray-200'

            return (
              <div key={i} className={msg.type === 'user' ? 'text-right' : 'text-left'}>
                <div className={`inline-block p-3 rounded-lg ${bubbleClass}`}>
                  <ReactMarkdown>{msg.text}</ReactMarkdown>
                  {msg.resources?.map((r, idx) => (
                    <a
                      key={idx}
                      href={r.link}
                      className="block text-blue-600 mt-1"
                      target="_blank"
                      rel="noopener noreferrer"
                    >
                      {r.title}
                    </a>
                  ))}
                </div>
              </div>
            )
          })
        )}
        <div ref={messagesEndRef} />
      </div>

      <form
        onSubmit={handleSubmit}
        className="p-4 bg-white border-t border-gray-300"
      >
        {stage === 'selection' && (
          <>
            <select
              value={selectedProblem}
              onChange={e => setSelectedProblem(e.target.value)}
              className="w-full p-2 border rounded"
            >
              <option value="">-- Select a topic --</option>
              {problems.map(p => (
                <option key={p.problem_id} value={p.problem_id}>
                  {p.problem_name}
                </option>
              ))}
            </select>
            <input
              type="text"
              value={userInput}
              onChange={e => setUserInput(e.target.value)}
              placeholder="Or type here..."
              className="w-full p-2 mt-2 border rounded"
            />
          </>
        )}

        {stage === 'chat' && (
          <input
            ref={inputRef}
            type="text"
            value={userInput}
            onChange={e => setUserInput(e.target.value)}
            placeholder="Your answer..."
            className="w-full p-2 border rounded"
          />
        )}

        {stage === 'conclusion' ? (
          <button
            type="button"
            onClick={reset}
            className="w-full p-2 bg-blue-500 text-white rounded mt-2"
          >
            Start Over
          </button>
        ) : (
          <button
            type="submit"
            disabled={
              loading ||
              (stage === 'selection' && !userInput && !selectedProblem)
            }
            className="w-full p-2 bg-blue-500 text-white rounded mt-2"
          >
            {sendLabel}
          </button>
        )}
      </form>
    </div>
  )
}

export default ChatWindow
