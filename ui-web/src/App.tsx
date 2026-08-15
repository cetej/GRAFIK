import SpikeStage from './spike/SpikeStage'
import EditorApp from './editor/EditorApp'
import './App.css'

// Spike stage stays reachable at /spike for benchmarking, but is no longer part of the
// production UI switcher (M6-UX1: operators never need to see it).
const isSpike = window.location.pathname === '/spike'

function App() {
  return isSpike ? <SpikeStage /> : <EditorApp />
}

export default App
