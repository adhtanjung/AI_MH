import ChatWindow from './components/ChatWindow';

function App() {
  return (
    <div className="min-h-screen bg-gradient-to-b from-neutral-50 to-neutral-100">
      <div className="container mx-auto px-4 py-10">
        {/* Logo and Title */}
        <div className="flex flex-col items-center mb-8">
          <div className="w-12 h-12 bg-blue-500 rounded-2xl flex items-center justify-center mb-3 shadow-sm">
            <svg xmlns="http://www.w3.org/2000/svg" className="h-6 w-6 text-white" fill="none" viewBox="0 0 24 24" stroke="currentColor">
              <path strokeLinecap="round" strokeLinejoin="round" strokeWidth={2} d="M13 10V3L4 14h7v7l9-11h-7z" />
            </svg>
          </div>
          <h1 className="text-2xl font-medium text-neutral-800 text-center">Mental Health Assessment</h1>
          <p className="text-neutral-500 text-center max-w-md mt-2">
            A confidential, AI-guided tool to help identify concerns and find appropriate resources
          </p>
        </div>

        {/* Main Chat Container with subtle shadow */}
        <div className="max-w-3xl mx-auto h-[600px] shadow-xl rounded-2xl overflow-hidden bg-white">
          <ChatWindow />
        </div>

        {/* Footer */}
        <div className="text-center mt-6 text-xs text-neutral-400">
          <p>© 2025 Mental Health Assessment Tool • <a href="#" className="text-blue-500 hover:underline">Privacy Policy</a> • <a href="#" className="text-blue-500 hover:underline">Terms of Use</a></p>
        </div>
      </div>
    </div>
  );
}

export default App;