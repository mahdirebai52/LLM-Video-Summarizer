import React, { useState } from 'react';

function StreamingProcessor({ token, onComplete }) {
  const [videoUrl, setVideoUrl] = useState('');
  const [status, setStatus] = useState('');
  const [transcript, setTranscript] = useState('');
  const [summary, setSummary] = useState('');
  const [isProcessing, setIsProcessing] = useState(false);
  const [error, setError] = useState('');

  const startProcessing = async (e) => {
    e.preventDefault();
    setIsProcessing(true);
    setError('');
    setStatus('');
    setTranscript('');
    setSummary('');

    try {
      const response = await fetch('http://localhost:5000/process-video-stream', {
        method: 'POST',
        headers: {
          'Content-Type': 'application/json',
          'Authorization': `Bearer ${token}`
        },
        body: JSON.stringify({ video_url: videoUrl })
      });

      const reader = response.body.getReader();
      const decoder = new TextDecoder();

      while (true) {
        const { done, value } = await reader.read();
        if (done) break;

        const chunk = decoder.decode(value);
        const lines = chunk.split('\n');

        for (const line of lines) {
          if (line.startsWith('data: ')) {
            try {
              const data = JSON.parse(line.slice(6));
              
              switch (data.type) {
                case 'status':
                  setStatus(data.message);
                  break;
                case 'transcript':
                  setTranscript(data.data);
                  break;
                case 'summary_chunk':
                  setSummary(prev => prev + data.data);
                  break;
                case 'complete':
                  setStatus('✅ Processing complete!');
                  setIsProcessing(false);
                  if (onComplete) onComplete();
                  break;
                case 'error':
                  setError(data.message);
                  setIsProcessing(false);
                  break;
              }
            } catch (e) {
              // Ignore JSON parse errors
            }
          }
        }
      }
    } catch (err) {
      setError('Failed to process video');
      setIsProcessing(false);
    }
  };

  return (
    <div className="glass-card rounded-2xl p-8">
      <h3 className="text-2xl font-bold text-gray-800 mb-6 flex items-center">
        <span className="text-3xl mr-3">🚀</span>
        Process New Video
      </h3>
      
      <form onSubmit={startProcessing} className="space-y-6">
        <div>
          <label className="block text-sm font-medium text-gray-700 mb-2">YouTube URL or Video ID</label>
          <input
            type="text"
            placeholder="https://www.youtube.com/watch?v=... or video_id"
            className="input-modern"
            value={videoUrl}
            onChange={(e) => setVideoUrl(e.target.value)}
            required
            disabled={isProcessing}
          />
        </div>
        
        <button
          type="submit"
          disabled={isProcessing}
          className="btn-primary w-full disabled:opacity-50 disabled:cursor-not-allowed"
        >
          {isProcessing ? (
            <div className="flex items-center justify-center">
              <div className="animate-spin rounded-full h-6 w-6 border-b-2 border-white mr-3"></div>
              <span>Processing...</span>
            </div>
          ) : (
            <span className="flex items-center justify-center">
              <span className="mr-2">⚡</span>
              Process Video
            </span>
          )}
        </button>
      </form>

      {/* Status */}
      {status && (
        <div className="mt-6 bg-blue-50 border border-blue-200 rounded-xl p-4">
          <p className="text-blue-600 font-medium">{status}</p>
        </div>
      )}

      {/* Error */}
      {error && (
        <div className="mt-6 bg-red-50 border border-red-200 rounded-xl p-4">
          <p className="text-red-600 font-medium">❌ {error}</p>
        </div>
      )}

      {/* Results */}
      {(transcript || summary) && (
        <div className="mt-8 grid md:grid-cols-2 gap-8">
          {transcript && (
            <div>
              <h4 className="text-lg font-semibold text-gray-800 mb-4 flex items-center">
                <span className="text-2xl mr-2">📄</span>
                Transcript
              </h4>
              <div className="bg-gray-50/80 backdrop-blur-sm rounded-xl p-6 max-h-80 overflow-y-auto border border-gray-200">
                <p className="text-gray-700 leading-relaxed whitespace-pre-wrap">{transcript}</p>
              </div>
            </div>
          )}
          
          {summary && (
            <div>
              <h4 className="text-lg font-semibold text-gray-800 mb-4 flex items-center">
                <span className="text-2xl mr-2">📝</span>
                Summary <span className="text-sm text-green-600 ml-2">(Live)</span>
              </h4>
              <div className="bg-gray-50/80 backdrop-blur-sm rounded-xl p-6 max-h-80 overflow-y-auto border border-gray-200">
                <p className="text-gray-700 leading-relaxed whitespace-pre-wrap">
                  {summary}
                  {isProcessing && <span className="animate-pulse">|</span>}
                </p>
              </div>
            </div>
          )}
        </div>
      )}
    </div>
  );
}

export default StreamingProcessor;