import { forwardRef, useEffect, useImperativeHandle, useRef } from 'react'
import * as THREE from 'three'
import { OrbitControls } from 'three/addons/controls/OrbitControls.js'
import { loadGlb } from './glb'

// Orbit viewer of the 3D tab (3D v2, sketch docs/spikes/img/2026-10-27-3d-v2-nacrt-1.png). three.js 0.170 as in
// KLAPKA prototypy/threejs-kolo. Shows engine viewer.opt.glb (decimated, clay, meshopt; else viewer.glb, src/glb.ts).
// The camera speaks the language of engine/blender/render_views.py --camera: target in glTF coordinates, azimuth
// 0° from +X and 90° from -Z (the sheet's azimuths), lens on a 36 mm sensor over a square frame, so "Použít tento
// pohled" renders this view.

export interface Cam3d { target: [number, number, number]; azimuth: number; elevation: number; distance: number; lens: number }
export interface ViewerHandle {
  view: (azimuth: number, elevation: number, k?: number) => void
  reset: () => void
  zoom: (factor: number) => void
  camera: () => Cam3d | null
}

const fovOf = (lens: number) => 2 * Math.atan(18 / lens) // vertical = horizontal on the square render
const deg = (r: number) => (r * 180) / Math.PI
const rad = (d: number) => (d * Math.PI) / 180

export const DEFAULT_VIEW = { azimuth: 315, elevation: 20 } // front three-quarter for models made from a front ref

const Viewer3d = forwardRef<ViewerHandle, {
  url: string
  fallback?: string
  lens: number
  onCamera: (c: Cam3d) => void
  onError: (msg: string) => void
}>(function Viewer3d({ url, fallback, lens, onCamera, onError }, ref) {
  const box = useRef<HTMLDivElement>(null)
  const st = useRef<{
    renderer: THREE.WebGLRenderer; cam: THREE.PerspectiveCamera; ctl: OrbitControls; scene: THREE.Scene
    sun: THREE.DirectionalLight; center: THREE.Vector3; size: number; ready: boolean; draw: () => void
  } | null>(null)
  const lensRef = useRef(lens)
  const cb = useRef({ onCamera, onError })
  cb.current = { onCamera, onError }

  const camera = (): Cam3d | null => {
    const s = st.current
    if (!s?.ready) return null
    const v = s.cam.position.clone().sub(s.ctl.target)
    const d = v.length()
    return {
      target: s.ctl.target.toArray() as [number, number, number],
      azimuth: (deg(Math.atan2(-v.z, v.x)) + 360) % 360,
      elevation: deg(Math.asin(v.y / d)),
      distance: d,
      lens: lensRef.current,
    }
  }

  const view = (azimuth: number, elevation: number, k = elevation < 50 ? 1.8 : 2.0) => {
    const s = st.current
    if (!s?.ready) return
    const a = rad(azimuth), e = rad(elevation)
    const dir = new THREE.Vector3(Math.cos(a) * Math.cos(e), Math.sin(e), -Math.sin(a) * Math.cos(e))
    // the sheet's distance is for 50 mm; a longer lens moves back so the object keeps its size in the frame
    s.cam.position.copy(s.center).addScaledVector(dir, s.size * k * (lensRef.current / 50))
    s.ctl.target.copy(s.center)
    s.ctl.update()
  }

  useImperativeHandle(ref, () => ({
    view,
    reset: () => view(DEFAULT_VIEW.azimuth, DEFAULT_VIEW.elevation),
    zoom: (f) => {
      const s = st.current
      if (!s?.ready) return
      s.cam.position.sub(s.ctl.target).multiplyScalar(f).add(s.ctl.target)
      s.ctl.update()
    },
    camera,
  }))

  useEffect(() => {
    const el = box.current!
    const renderer = new THREE.WebGLRenderer({ antialias: true, alpha: true, preserveDrawingBuffer: true })
    renderer.setPixelRatio(Math.min(window.devicePixelRatio, 2))
    el.prepend(renderer.domElement)
    const scene = new THREE.Scene()
    scene.add(new THREE.HemisphereLight(0xffffff, 0x9a9a9a, 1.7))
    const sun = new THREE.DirectionalLight(0xffffff, 2.0)
    scene.add(sun, sun.target)
    const cam = new THREE.PerspectiveCamera(45, 1, 0.01, 1000)
    const ctl = new OrbitControls(cam, renderer.domElement) // left = rotate, wheel = zoom, Shift+left / right = pan
    const s = { renderer, cam, ctl, scene, sun, center: new THREE.Vector3(), size: 1, ready: false, draw: () => {} }
    s.draw = () => {
      // key light from behind the camera, a little left and above, as in render_views.py
      const back = cam.position.clone().sub(ctl.target)
      sun.position.copy(ctl.target).add(back.applyAxisAngle(new THREE.Vector3(0, 1, 0), rad(25))).add(new THREE.Vector3(0, 0.6 * s.size, 0))
      sun.target.position.copy(ctl.target)
      renderer.render(scene, cam)
      const c = camera()
      if (c) cb.current.onCamera(c)
    }
    st.current = s
    const fit = () => {
      const w = el.clientWidth, h = el.clientHeight
      if (!w || !h) return
      renderer.setSize(w, h, false)
      cam.aspect = w / h
      // the square frame spans the shorter side: on a tall viewer widen the vertical angle to keep it
      const f = fovOf(lensRef.current)
      cam.fov = deg(cam.aspect >= 1 ? f : 2 * Math.atan(Math.tan(f / 2) / cam.aspect))
      cam.updateProjectionMatrix()
      s.draw()
    }
    ctl.addEventListener('change', s.draw)
    const ro = new ResizeObserver(fit)
    ro.observe(el)
    fit()

    let gone = false
    const meshes: THREE.Mesh[] = []
    loadGlb(url, fallback).then((root) => {
      if (gone) return
      let tris = 0
      root.traverse((o) => {
        const m = o as THREE.Mesh
        if (m.isMesh) {
          meshes.push(m)
          tris += (m.geometry.index?.count ?? m.geometry.attributes.position.count) / 3
        }
      })
      // generated meshes (100k triangles) look right smooth; hand-made low-poly ones need their hard edges
      const mat = new THREE.MeshStandardMaterial({ color: 0xd2cdc4, roughness: 0.9, flatShading: tris < 20000 })
      for (const m of meshes) {
        if (!m.geometry.attributes.normal) m.geometry.computeVertexNormals()
        m.material = mat
      }
      scene.add(root)
      const b = new THREE.Box3().setFromObject(root)
      b.getCenter(s.center)
      s.size = Math.max(...b.getSize(new THREE.Vector3()).toArray())
      cam.near = s.size / 100
      cam.far = s.size * 100
      cam.updateProjectionMatrix()
      ctl.minDistance = s.size * 0.3
      ctl.maxDistance = s.size * 10
      s.ready = true
      view(DEFAULT_VIEW.azimuth, DEFAULT_VIEW.elevation)
    }, (e) => cb.current.onError(`Model se do prohlížeče nenačetl: ${(e as Error).message ?? e}`))

    return () => {
      gone = true
      ro.disconnect()
      ctl.dispose()
      for (const m of meshes) m.geometry.dispose()
      renderer.dispose()
      renderer.domElement.remove()
      st.current = null
    }
  }, [url]) // eslint-disable-line react-hooks/exhaustive-deps

  useEffect(() => {
    // a new lens keeps the framing: the camera moves back or forward with the focal length
    const s = st.current
    const old = lensRef.current
    lensRef.current = lens
    if (!s) return
    const f = fovOf(lens)
    s.cam.fov = deg(s.cam.aspect >= 1 ? f : 2 * Math.atan(Math.tan(f / 2) / s.cam.aspect))
    s.cam.updateProjectionMatrix()
    if (s.ready && old !== lens) {
      s.cam.position.sub(s.ctl.target).multiplyScalar(lens / old).add(s.ctl.target)
      s.ctl.update()
    }
    s.draw()
  }, [lens])

  return (
    <div className="viewer3d" ref={box}>
      <span className="howto">táhnout = otočit · kolečko = přiblížit · Shift+táhnout = posunout</span>
      <div className="frame"><span>výřez předlohy (čtverec)</span></div>
    </div>
  )
})

export default Viewer3d
