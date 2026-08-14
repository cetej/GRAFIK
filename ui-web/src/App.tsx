import { useState } from 'react'
import SpikeStage from './spike/SpikeStage'
import EditorApp from './editor/EditorApp'
import './App.css'

type View = 'editor' | 'spike'

function App() {
  const [view, setView] = useState<View>('editor')

  return (
    <>
      <div className="view-switch">
        <button
          className={view === 'editor' ? 'active' : ''}
          onClick={() => setView('editor')}
        >
          Editor
        </button>
        <button
          className={view === 'spike' ? 'active' : ''}
          onClick={() => setView('spike')}
        >
          Spike
        </button>
      </div>
      {view === 'editor' ? <EditorApp /> : <SpikeStage />}
    </>
  )
}

export default App
