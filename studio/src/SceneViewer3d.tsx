import { forwardRef, useEffect, useImperativeHandle, useRef } from 'react'
import * as THREE from 'three'
import { OrbitControls } from 'three/addons/controls/OrbitControls.js'
import { GLTFLoader } from 'three/addons/loaders/GLTFLoader.js'
import type { Cam3d } from './Viewer3d.tsx'

// Viewer of a 3D scene (brief B, sketch docs/spikes/img/2026-10-27-3d-sceny-nacrt.png). Places the objects exactly
// as engine/blender/render_views.py --scene does — a model scaled uniformly to its longest side `rozmer`, bottom
// centre on `misto` (x, y on the ground, z up = three.js x, -z), turned `otoceni` about the vertical, standing on
// the top of the object `na` names; a change in one needs the same change in the other. The camera speaks the
// language of Viewer3d / render_views.py --camera, and the 36 mm sensor spans the longer side of the frame, as
// Blender's sensor_fit AUTO does, so the dashed frame is exactly the still.

export interface SceneItem {
  key: string          // object id, or 'postava'
  url?: string         // GLB (viewer.glb of the model version, or the figure)
  box?: number[]       // simple shape: kvadr [x, y, z] / valec [d, h]
  shape?: 'kvadr' | 'valec'
  rozmer?: number
  misto: [number, number]
  otoceni: number
  na: string | null
  figure?: boolean
}
export interface SceneViewerHandle {
  view: (azimuth: number, elevation: number) => void
  fit: () => void
  zoom: (factor: number) => void
  camera: () => Cam3d | null
  setCamera: (c: Cam3d) => void
}

const deg = (r: number) => (r * 180) / Math.PI
const rad = (d: number) => (d * Math.PI) / 180
const SNAP = 0.1
const clay = new THREE.MeshStandardMaterial({ color: 0xd2cdc4, roughness: 0.9 })
const selClay = new THREE.MeshStandardMaterial({ color: 0xa9bde6, roughness: 0.9 })
const figClay = new THREE.MeshStandardMaterial({ color: 0xc2410c, roughness: 0.8 })

export function frameRect(w: number, h: number, aspect: number) {
  const fw = Math.min(w, h * aspect)
  return { w: fw, h: fw / aspect }
}

const SceneViewer3d = forwardRef<SceneViewerHandle, {
  items: SceneItem[]
  selected: string | null
  aspect: number
  lens: number
  onSelect: (key: string | null) => void
  onMove: (key: string, misto: [number, number]) => void
  onTurn: (key: string, deltaDeg: number) => void
  onCamera: (c: Cam3d) => void
  onError: (msg: string) => void
}>(function SceneViewer3d(props, ref) {
  const box = useRef<HTMLDivElement>(null)
  const frameEl = useRef<HTMLDivElement>(null)
  const cb = useRef(props)
  cb.current = props
  const st = useRef<{
    renderer: THREE.WebGLRenderer; cam: THREE.PerspectiveCamera; ctl: OrbitControls; scene: THREE.Scene
    sun: THREE.DirectionalLight; root: THREE.Group; groups: Map<string, THREE.Group>; cache: Map<string, Promise<THREE.Object3D>>
    draw: () => void; fitCam: () => void; size: number
  } | null>(null)
  const fitted = useRef(false)

  const camera = (): Cam3d | null => {
    const s = st.current
    if (!s) return null
    const v = s.cam.position.clone().sub(s.ctl.target)
    const d = v.length()
    return { target: s.ctl.target.toArray() as [number, number, number], azimuth: (deg(Math.atan2(-v.z, v.x)) + 360) % 360,
      elevation: deg(Math.asin(v.y / d)), distance: d, lens: cb.current.lens }
  }
  const setCamera = (c: Cam3d) => {
    const s = st.current
    if (!s) return
    const a = rad(c.azimuth), e = rad(c.elevation)
    s.ctl.target.fromArray(c.target)
    s.cam.position.copy(s.ctl.target).add(new THREE.Vector3(Math.cos(a) * Math.cos(e), Math.sin(e), -Math.sin(a) * Math.cos(e)).multiplyScalar(c.distance))
    s.ctl.update()
  }
  const sceneBox = () => {
    const s = st.current!
    const b = new THREE.Box3()
    for (const g of s.groups.values()) b.expandByObject(g)
    return b.isEmpty() ? new THREE.Box3(new THREE.Vector3(-5, 0, -5), new THREE.Vector3(5, 2, 5)) : b
  }
  const view = (azimuth: number, elevation: number) => {
    const s = st.current
    if (!s) return
    const b = sceneBox()
    const c = b.getCenter(new THREE.Vector3())
    const size = Math.max(...b.getSize(new THREE.Vector3()).toArray())
    setCamera({ target: c.toArray() as [number, number, number], azimuth, elevation, distance: size * 1.7 * (cb.current.lens / 50), lens: cb.current.lens })
  }

  useImperativeHandle(ref, () => ({
    view, camera, setCamera,
    fit: () => { const c = camera(); view(c?.azimuth ?? 305, c?.elevation ?? 22) },
    zoom: (f) => {
      const s = st.current
      if (!s) return
      s.cam.position.sub(s.ctl.target).multiplyScalar(f).add(s.ctl.target)
      s.ctl.update()
    },
  }))

  useEffect(() => {
    const el = box.current!
    const renderer = new THREE.WebGLRenderer({ antialias: true, preserveDrawingBuffer: true })
    renderer.setPixelRatio(Math.min(window.devicePixelRatio, 2))
    renderer.setClearColor(0xcdd0d5)
    el.prepend(renderer.domElement)
    const scene = new THREE.Scene()
    scene.add(new THREE.HemisphereLight(0xffffff, 0x9a9a9a, 1.7))
    const sun = new THREE.DirectionalLight(0xffffff, 2.0)
    scene.add(sun, sun.target)
    const grid1 = new THREE.GridHelper(200, 200, 0xb3b8c1, 0xb9bec7)
    const grid10 = new THREE.GridHelper(200, 20, 0x8a919e, 0x8a919e)
    grid10.position.y = 0.01
    scene.add(grid1, grid10)
    const root = new THREE.Group()
    scene.add(root)
    const cam = new THREE.PerspectiveCamera(30, 1, 0.05, 5000)
    const ctl = new OrbitControls(cam, renderer.domElement)
    ctl.maxPolarAngle = rad(89.5)
    const s = { renderer, cam, ctl, scene, sun, root, groups: new Map(), cache: new Map(), draw: () => {}, fitCam: () => {}, size: 10 }
    s.draw = () => {
      const back = cam.position.clone().sub(ctl.target)
      sun.position.copy(ctl.target).add(back.applyAxisAngle(new THREE.Vector3(0, 1, 0), rad(25))).add(new THREE.Vector3(0, back.length() * 0.3, 0))
      sun.target.position.copy(ctl.target)
      renderer.render(scene, cam)
      const c = camera()
      if (c) cb.current.onCamera(c)
    }
    s.fitCam = () => {
      const w = el.clientWidth, h = el.clientHeight
      if (!w || !h) return
      renderer.setSize(w, h, false)
      cam.aspect = w / h
      // the frame of the still inside the canvas; its longer side spans the 36 mm sensor (Blender AUTO fit)
      const fr = frameRect(w, h, cb.current.aspect)
      const t = 18 / cb.current.lens
      cam.fov = deg(2 * Math.atan((h * t) / Math.max(fr.w, fr.h)))
      cam.updateProjectionMatrix()
      if (frameEl.current) Object.assign(frameEl.current.style, { width: `${fr.w}px`, height: `${fr.h}px` })
      s.draw()
    }
    st.current = s
    ctl.addEventListener('change', s.draw)
    const ro = new ResizeObserver(s.fitCam)
    ro.observe(el)

    // pick and drag on the ground; a drag that starts on empty space orbits
    const ray = new THREE.Raycaster()
    const ndc = (e: PointerEvent) => {
      const r = renderer.domElement.getBoundingClientRect()
      return new THREE.Vector2(((e.clientX - r.left) / r.width) * 2 - 1, -((e.clientY - r.top) / r.height) * 2 + 1)
    }
    let drag: { key: string; plane: THREE.Plane; off: THREE.Vector3; moved: boolean } | null = null
    const down = (e: PointerEvent) => {
      if (e.button !== 0 || e.shiftKey) return
      ray.setFromCamera(ndc(e), cam)
      const hit = ray.intersectObjects(root.children, true)[0]
      let o: THREE.Object3D | null = hit?.object ?? null
      while (o && !o.userData.key) o = o.parent
      if (!o) { cb.current.onSelect(null); return }
      const key = o.userData.key as string
      cb.current.onSelect(key)
      const plane = new THREE.Plane(new THREE.Vector3(0, 1, 0), -o.position.y)
      const p = new THREE.Vector3()
      ray.ray.intersectPlane(plane, p)
      drag = { key, plane, off: o.position.clone().sub(p), moved: false }
      ctl.enabled = false
      renderer.domElement.setPointerCapture(e.pointerId)
    }
    const move = (e: PointerEvent) => {
      if (!drag) return
      ray.setFromCamera(ndc(e), cam)
      const p = new THREE.Vector3()
      if (!ray.ray.intersectPlane(drag.plane, p)) return
      p.add(drag.off)
      const g = s.groups.get(drag.key)
      if (!g) return
      g.position.x = Math.round(p.x / SNAP) * SNAP
      g.position.z = Math.round(p.z / SNAP) * SNAP
      drag.moved = true
      s.draw()
    }
    const up = () => {
      if (!drag) return
      const g = s.groups.get(drag.key)
      if (drag.moved && g) cb.current.onMove(drag.key, [+g.position.x.toFixed(2), +(-g.position.z).toFixed(2)])
      drag = null
      ctl.enabled = true
    }
    const key = (e: KeyboardEvent) => {
      const k = cb.current.selected
      if (!k || (e.target as HTMLElement).closest('input, select, textarea')) return
      if (e.key === 'q' || e.key === 'Q') cb.current.onTurn(k, 15)
      if (e.key === 'e' || e.key === 'E') cb.current.onTurn(k, -15)
    }
    const c = renderer.domElement
    c.addEventListener('pointerdown', down, true)   // before OrbitControls, so a drag on an object does not orbit
    c.addEventListener('pointermove', move)
    c.addEventListener('pointerup', up)
    window.addEventListener('keydown', key)
    s.fitCam()
    return () => {
      ro.disconnect()
      ctl.dispose()
      c.removeEventListener('pointerdown', down, true)
      window.removeEventListener('keydown', key)
      renderer.dispose()
      renderer.domElement.remove()
      st.current = null
    }
  }, [])

  // lens / frame changes: same framing rule as on mount
  useEffect(() => { st.current?.fitCam() }, [props.lens, props.aspect])

  // (re)place the objects whenever the scene changes; GLBs load once per URL
  useEffect(() => {
    const s = st.current
    if (!s) return
    let gone = false
    const load = (url: string) => {
      if (!s.cache.has(url)) {
        s.cache.set(url, new Promise((ok, bad) => new GLTFLoader().load(url, (g) => ok(g.scene), undefined, bad)))
      }
      return s.cache.get(url)!
    }
    Promise.all(props.items.map(async (it) => {
      if (it.url) {
        try { return (await load(it.url)).clone(true) } catch (e) {
          cb.current.onError(`Model ${it.key} se do prohlížeče nenačetl: ${(e as Error).message ?? e}`)
          return null
        }
      }
      const b = it.box!
      const geo = it.shape === 'valec' ? new THREE.CylinderGeometry(b[0] / 2, b[0] / 2, b[1], 48) : new THREE.BoxGeometry(b[0], b[2], b[1])
      return new THREE.Mesh(geo) as THREE.Object3D
    })).then((objs) => {
      if (gone) return
      s.root.clear()
      s.groups.clear()
      const placed = new Map<string, THREE.Group>()
      props.items.forEach((it, i) => {
        const o = objs[i]
        if (!o) return
        const mat = it.figure ? figClay : it.key === cb.current.selected ? selClay : clay
        o.traverse((m) => {
          const mesh = m as THREE.Mesh
          if (mesh.isMesh) {
            if (!mesh.geometry.attributes.normal) mesh.geometry.computeVertexNormals()
            mesh.material = mat
          }
        })
        const inner = new THREE.Group()
        inner.add(o)
        o.position.set(0, 0, 0)
        o.scale.set(1, 1, 1)
        let bb = new THREE.Box3().setFromObject(o)
        const k = it.url && it.rozmer ? it.rozmer / Math.max(...bb.getSize(new THREE.Vector3()).toArray()) : 1
        inner.scale.setScalar(k)
        bb = new THREE.Box3().setFromObject(inner)
        const c = bb.getCenter(new THREE.Vector3())
        inner.position.set(-c.x, -bb.min.y, -c.z)
        const g = new THREE.Group()
        g.add(inner)
        g.userData.key = it.key
        const base = it.na && placed.has(it.na) ? new THREE.Box3().setFromObject(placed.get(it.na)!).max.y : 0
        g.position.set(it.misto[0], base, -it.misto[1])
        g.rotation.y = rad(it.otoceni)
        s.root.add(g)
        g.updateMatrixWorld(true)
        placed.set(it.key, g)
        s.groups.set(it.key, g)
        if (it.key === cb.current.selected) {
          const h = new THREE.Box3Helper(new THREE.Box3().setFromObject(g), 0x1f5fd1)
          h.raycast = () => {}   // picking goes to the objects, never to the outline
          s.root.add(h)
        }
      })
      if (!fitted.current && props.items.length) {
        fitted.current = true
        if (!s.cam.position.lengthSq()) view(305, 22)   // no saved camera was set: frame the whole scene
      }
      s.draw()
    })
    return () => { gone = true }
  }, [JSON.stringify(props.items), props.selected]) // eslint-disable-line react-hooks/exhaustive-deps

  return (
    <div className="viewer3d scene3d" ref={box}>
      <span className="howto">táhnout objekt = posunout (po 0,1 m) · Q / E = otočit o 15° · táhnout mimo = otočit pohled · Shift+táhnout = posunout pohled</span>
      <div className="frame" ref={frameEl}><span>rámeček snímku</span></div>
    </div>
  )
})

export default SceneViewer3d
