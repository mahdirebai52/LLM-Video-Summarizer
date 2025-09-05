import React, { useState, useEffect } from 'react';
import axios from 'axios';

function Dashboard({ token, setToken }) {
  const [videoUrl, setVideoUrl] = useState('');
  const [result, setResult] = useState(null);
  const [loading, setLoading] = useState(false);
  const [error, setError] = useState('');
  const [videos, setVideos] = useState([]);

  useEffect(() => {
    fetchUserVideos();
  }, []);

  const fetchUserVideos = async () => {
    try {
      const response = await axios.get('http://localhost:5000/my-videos', {
        headers: { Authorization: `Bearer ${token}` }
      });
      setVideos(response.data.videos);
    } catch (err) {
      console.error('Failed to fetch videos');
    }
  };

  const handleSubmit = async (e) => {
    e.preventDefault();
    setLoading(true);
    setError('');
    setResult(null);

    try {
      const response = await axios.post(
        'http://localhost:5000/process-video',
        { video_url: videoUrl },
        { headers: { Authorization: `Bearer ${token}` } }
      );
      setResult(response.data);
      setVideoUrl('');
      fetchUserVideos();
    } catch (err) {
      setError(err.response?.data?.error || 'Processing failed');
    } finally {
      setLoading(false);
    }
  };

  const handleLogout = () => {
    setToken(null);
  };

  return (
    <div className="min-h-screen">
      {/* Header */}
      <div className="glass-card border-b border-white/20">
        <div className="max-w-7xl mx-auto px-6 py-4">
          <div className="flex justify-between items-center">
            <div className="flex items-center space-x-4">
              <div className="w-12 h-12 bg-gradient-to-r from-blue-500 to-indigo-600 rounded-xl flex items-center justify-center shadow-lg">
                <span className="text-2xl">🎬</span>
              </div>
              <div>
                <h1 className="text-2xl font-bold text-gray-800">Video to Text</h1>
                <p className="text-gray-600 text-sm">AI-powered transcription</p>
              </div>
            </div>
            <button
              onClick={handleLogout}
              className="bg-red-500 hover:bg-red-600 text-white font-semibold py-2 px-4 rounded-lg transition-colors duration-200"
            >
              Logout
            </button>
          </div>
        </div>
      </div>

      <div className="max-w-7xl mx-auto p-6 space-y-8">
        
        {/* Video Processing Card */}
        <div className="glass-card rounded-2xl p-8">
          <h3 className="text-2xl font-bold text-gray-800 mb-6 flex items-center">
            <span className="text-3xl mr-3">🚀</span>
            Process New Video
          </h3>
          
          <form onSubmit={handleSubmit} className="space-y-6">
            <div>
              <label className="block text-sm font-medium text-gray-700 mb-2">YouTube URL or Video ID</label>
              <input
                type="text"
                placeholder="https://www.youtube.com/watch?v=... or video_id"
                className="input-modern"
                value={videoUrl}
                onChange={(e) => setVideoUrl(e.target.value)}
                required
              />
            </div>
            
            <button
              type="submit"
              disabled={loading}
              className="btn-primary w-full disabled:opacity-50 disabled:cursor-not-allowed"
            >
              {loading ? (
                <div className="flex items-center justify-center">
                  <div className="animate-spin rounded-full h-6 w-6 border-b-2 border-white mr-3"></div>
                  <span>Processing... This may take a few minutes</span>
                </div>
              ) : (
                <span className="flex items-center justify-center">
                  <span className="mr-2">⚡</span>
                  Process Video
                </span>
              )}
            </button>
          </form>

          {error && (
            <div className="mt-6 bg-red-50 border border-red-200 rounded-xl p-4">
              <p className="text-red-600 font-medium">❌ {error}</p>
            </div>
          )}
        </div>

        {/* Processing Result */}
        {result && (
          <div className="glass-card rounded-2xl p-8 animate-fade-in">
            <h3 className="text-2xl font-bold text-gray-800 mb-6 flex items-center">
              <span className="text-3xl mr-3">✅</span>
              {result.video_title}
            </h3>
            
            <div className="grid md:grid-cols-2 gap-8">
              <div>
                <h4 className="text-lg font-semibold text-gray-800 mb-4 flex items-center">
                  <span className="text-2xl mr-2">📄</span>
                  Transcript
                </h4>
                <div className="bg-gray-50/80 backdrop-blur-sm rounded-xl p-6 max-h-80 overflow-y-auto border border-gray-200">
                  <p className="text-gray-700 leading-relaxed whitespace-pre-wrap">{result.transcript}</p>
                </div>
              </div>
              
              <div>
                <h4 className="text-lg font-semibold text-gray-800 mb-4 flex items-center">
                  <span className="text-2xl mr-2">📝</span>
                  Summary
                </h4>
                <div className="bg-gray-50/80 backdrop-blur-sm rounded-xl p-6 max-h-80 overflow-y-auto border border-gray-200">
                  <p className="text-gray-700 leading-relaxed whitespace-pre-wrap">{result.summary}</p>
                </div>
              </div>
            </div>
          </div>
        )}

        {/* Previous Videos */}
        <div className="glass-card rounded-2xl p-8">
          <h3 className="text-2xl font-bold text-gray-800 mb-6 flex items-center">
            <span className="text-3xl mr-3">📁</span>
            Your Videos ({videos.length})
          </h3>
          
          {videos.length === 0 ? (
            <div className="text-center py-12">
              <div className="text-6xl mb-4">🎥</div>
              <p className="text-gray-500 text-lg">No videos processed yet</p>
              <p className="text-gray-400">Upload your first video to get started!</p>
            </div>
          ) : (
            <div className="grid gap-6">
              {videos.map((video, index) => (
                <div key={index} className="bg-white/60 backdrop-blur-sm border border-gray-200 rounded-xl p-6 hover:shadow-lg transition-all duration-200">
                  <div className="flex justify-between items-start mb-4">
                    <h4 className="font-semibold text-gray-800 text-lg">{video.title}</h4>
                    <span className="text-sm text-gray-500 bg-gray-100 px-3 py-1 rounded-full">
                      {new Date(video.date).toLocaleDateString()}
                    </span>
                  </div>
                  
                  <div className="grid md:grid-cols-2 gap-6">
                    <div>
                      <p className="text-sm font-medium text-gray-700 mb-2 flex items-center">
                        <span className="mr-1">📄</span> Transcript Preview
                      </p>
                      <p className="text-sm text-gray-600 bg-gray-50 p-3 rounded-lg">
                        {video.transcript.substring(0, 150)}...
                      </p>
                    </div>
                    
                    <div>
                      <p className="text-sm font-medium text-gray-700 mb-2 flex items-center">
                        <span className="mr-1">📝</span> Summary Preview
                      </p>
                      <p className="text-sm text-gray-600 bg-gray-50 p-3 rounded-lg">
                        {video.summary.substring(0, 150)}...
                      </p>
                    </div>
                  </div>
                </div>
              ))}
            </div>
          )}
        </div>

      </div>
    </div>
  );
}

export default Dashboard;