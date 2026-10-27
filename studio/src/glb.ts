import type * as THREE from 'three'
import { GLTFLoader } from 'three/addons/loaders/GLTFLoader.js'
import { MeshoptDecoder } from 'three/addons/libs/meshopt_decoder.module.js'

// viewer.opt.glb is quantized + meshopt (engine/models3d.py OPTIMIZE_ARGS); when it is missing or does not load,
// the viewers fall back to viewer.glb, which the optimizer never touches.
const loader = new GLTFLoader().setMeshoptDecoder(MeshoptDecoder)

const one = (url: string) => new Promise<THREE.Group>((ok, bad) => loader.load(url, (g) => ok(g.scene), undefined, bad))

export function loadGlb(url: string, fallback?: string): Promise<THREE.Group> {
  if (!fallback || fallback === url) return one(url)
  return one(url).catch((e) => {
    console.warn(`optimalizovaný model se nenačetl (${(e as Error).message ?? e}), načítám ${fallback}`)
    return one(fallback)
  })
}
