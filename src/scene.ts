import * as THREE from 'three'

/** An authored, explorable example inspired by the supplied showroom photograph. */
export function createExampleScene(): THREE.Group {
  const scene = new THREE.Group()
  scene.name = 'Industrial showroom example'

  const mat = (color: THREE.ColorRepresentation, roughness = .6, metalness = 0) =>
    new THREE.MeshStandardMaterial({ color, roughness, metalness })
  const warmWhite = mat('#dddace', .82)
  const columnWhite = mat('#e9e7de', .66)
  const steel = mat('#161c23', .53, .55)
  const roof = mat('#252b31', .8, .3)
  const rubber = mat('#121416', .82)
  const trim = mat('#202529', .48, .18)
  const chrome = mat('#b8c2c8', .22, .83)
  const darkChrome = mat('#505b64', .3, .75)
  const glass = new THREE.MeshStandardMaterial({ color: '#152a34', roughness: .13, metalness: .56 })
  const headlight = new THREE.MeshStandardMaterial({ color: '#e1edf0', emissive: '#b7d1e2', emissiveIntensity: .17, roughness: .2, metalness: .28 })
  const tailLight = new THREE.MeshStandardMaterial({ color: '#b42820', emissive: '#92170f', emissiveIntensity: .2, roughness: .26 })

  function mesh(geometry: THREE.BufferGeometry, material: THREE.Material, parent: THREE.Object3D, x = 0, y = 0, z = 0): THREE.Mesh {
    const object = new THREE.Mesh(geometry, material)
    object.position.set(x, y, z)
    object.castShadow = true
    object.receiveShadow = true
    parent.add(object)
    return object
  }

  function box(parent: THREE.Object3D, material: THREE.Material, w: number, h: number, d: number, x = 0, y = 0, z = 0): THREE.Mesh {
    return mesh(new THREE.BoxGeometry(w, h, d), material, parent, x, y, z)
  }

  function softBox(parent: THREE.Object3D, material: THREE.Material, w: number, h: number, d: number, x = 0, y = 0, z = 0, radius = .06): THREE.Mesh {
    const r = Math.min(radius, w / 4, h / 4, d / 4)
    const shape = new THREE.Shape()
    const left = -w / 2 + r, right = w / 2 - r, bottom = -h / 2 + r, top = h / 2 - r
    shape.moveTo(left, bottom - r)
    shape.lineTo(right, bottom - r)
    shape.quadraticCurveTo(right + r, bottom - r, right + r, bottom)
    shape.lineTo(right + r, top)
    shape.quadraticCurveTo(right + r, top + r, right, top + r)
    shape.lineTo(left, top + r)
    shape.quadraticCurveTo(left - r, top + r, left - r, top)
    shape.lineTo(left - r, bottom)
    shape.quadraticCurveTo(left - r, bottom - r, left, bottom - r)
    const geometry = new THREE.ExtrudeGeometry(shape, { depth: d - 2 * r, bevelEnabled: true, bevelThickness: r, bevelSize: r * .5, bevelSegments: 2, steps: 1, curveSegments: 3 })
    geometry.translate(0, 0, -(d - 2 * r) / 2)
    return mesh(geometry, material, parent, x, y, z)
  }

  function cylinder(parent: THREE.Object3D, material: THREE.Material, radius: number, length: number, x: number, y: number, z: number, segments = 24): THREE.Mesh {
    const object = mesh(new THREE.CylinderGeometry(radius, radius, length, segments), material, parent, x, y, z)
    object.rotation.z = Math.PI / 2
    return object
  }

  // The small deterministic flecks make the poured floor readable at walking height.
  const canvas = document.createElement('canvas')
  canvas.width = canvas.height = 1024
  const context = canvas.getContext('2d')!
  context.fillStyle = '#58636d'
  context.fillRect(0, 0, 1024, 1024)
  let seed = 7319
  const random = () => {
    seed = (Math.imul(seed, 1664525) + 1013904223) | 0
    return (seed >>> 0) / 4294967296
  }
  const flakes = ['#d1d4d3', '#9fa9b0', '#25333e', '#f0e9d7', '#78848e', '#3a4a58']
  for (let i = 0; i < 53000; i++) {
    const x = random() * 1024, y = random() * 1024
    const size = .65 + random() * 3.2
    context.fillStyle = flakes[Math.floor(random() * flakes.length)]
    context.beginPath()
    context.moveTo(x, y)
    context.lineTo(x + size, y + size * .24)
    context.lineTo(x + size * .55, y + size)
    context.lineTo(x - size * .3, y + size * .48)
    context.fill()
  }
  const floorMap = new THREE.CanvasTexture(canvas)
  floorMap.colorSpace = THREE.SRGBColorSpace
  floorMap.wrapS = floorMap.wrapT = THREE.RepeatWrapping
  floorMap.repeat.set(5, 6.5)
  floorMap.anisotropy = 8
  const floor = new THREE.MeshStandardMaterial({ map: floorMap, color: '#c3cbd1', roughness: .36, metalness: .14 })
  box(scene, mat('#626969', .95), 90, .14, 85, 8, -.2, -14)
  box(scene, floor, 20, .14, 26, 0, -.07, -6)
  box(scene, mat('#b4b4a9', .85), 20, .055, .14, 0, .015, 7)
  box(scene, warmWhite, .25, 6.5, 26, -10.1, 3.25, -6)
  box(scene, warmWhite, 20, 6.5, .25, 0, 3.25, -19.1)
  box(scene, roof, 20.6, .13, 26.5, 0, 6.64, -6)

  // Exposed roof structure and the continuous high window band along the left wall.
  for (let z = -18.5; z <= 7; z += 1.25) box(scene, steel, 20.5, .095, .07, 0, 6.52, z)
  for (const x of [-10, -5, 0, 5, 10]) box(scene, steel, .16, .26, 26.5, x, 6.36, -6)
  for (const z of [-18.7, -12.5, -6.2, 0, 6.4]) {
    box(scene, steel, 20.5, .42, .2, 0, 6.12, z)
    // Thin lower chord and diagonal braces reveal the truss depth.
    box(scene, steel, 20.5, .08, .12, 0, 5.74, z)
    for (let x = -9; x < 10; x += 2.5) {
      const brace = box(scene, steel, 1.28, .045, .06, x, 5.94, z)
      brace.rotation.z = x % 2 === 0 ? .3 : -.3
    }
  }
  box(scene, trim, .035, .85, 24.3, -9.95, 3.8, -6.4)
  box(scene, glass, .045, .71, 24, -9.92, 3.8, -6.4)
  for (let z = -18; z < 6; z += 1.15) box(scene, steel, .07, .84, .045, -9.88, 3.8, z)
  for (const z of [-18.7, -10.3, -2, 6.4]) {
    box(scene, columnWhite, .58, 6.3, .64, 9.72, 3.15, z)
    box(scene, warmWhite, .68, .14, .74, 9.72, .07, z)
  }
  box(scene, columnWhite, .55, 6.25, .62, -1.4, 3.12, -18.82)

  // Windowed workshop door on the rear wall.
  box(scene, steel, 4.6, 3.9, .14, -5.4, 1.95, -18.87)
  box(scene, glass, 4.33, 3.6, .05, -5.4, 1.95, -18.77)
  for (let y = .3; y < 3.9; y += .72) box(scene, trim, 4.42, .065, .06, -5.4, y, -18.71)
  for (const x of [-6.85, -5.4, -3.95]) box(scene, trim, .06, 3.65, .06, x, 1.95, -18.71)

  // Small warm practical lamps are meshes, keeping the scene inexpensive to light.
  const lampMat = new THREE.MeshStandardMaterial({ color: '#fff3d2', emissive: '#fff1cb', emissiveIntensity: 2.2 })
  for (const z of [-15, -7, 1]) {
    for (const x of [-5, 4.5]) {
      cylinder(scene, steel, .018, .3, x, 6.02, z).rotation.set(0, 0, 0)
      const shade = mesh(new THREE.ConeGeometry(.27, .12, 24, 1, true), steel, scene, x, 5.83, z)
      shade.rotation.x = Math.PI
      const diffuser = mesh(new THREE.CircleGeometry(.21, 24), lampMat, scene, x, 5.78, z)
      diffuser.rotation.x = -Math.PI / 2
    }
  }

  function wheel(parent: THREE.Object3D, x: number, z: number, scale = 1, sporty = false): void {
    const y = .53 * scale
    const radius = .52 * scale
    cylinder(parent, rubber, radius, .3 * scale, x, y, z, 32)
    const faceX = x + Math.sign(x) * .161 * scale
    cylinder(parent, darkChrome, radius * .72, .025, faceX, y, z, 28)
    const rim = mesh(new THREE.TorusGeometry(radius * .71, .026 * scale, 5, 32), chrome, parent, faceX + Math.sign(x) * .018, y, z)
    rim.rotation.y = Math.PI / 2
    cylinder(parent, trim, radius * .55, .03, faceX + Math.sign(x) * .02, y, z)
    for (let spoke = 0; spoke < (sporty ? 10 : 5); spoke++) {
      const angle = spoke * Math.PI * 2 / (sporty ? 10 : 5)
      const part = box(parent, sporty ? darkChrome : chrome, .04, radius * .64, .055 * scale,
        faceX + Math.sign(x) * .045, y + Math.cos(angle) * radius * .31, z + Math.sin(angle) * radius * .31)
      part.rotation.x = -angle
    }
    cylinder(parent, chrome, radius * .16, .05, faceX + Math.sign(x) * .06, y, z, 16)
  }

  function suv(color: string, x: number, z: number, angle = 0): void {
    const car = new THREE.Group()
    car.position.set(x, .01, z)
    car.rotation.y = angle
    scene.add(car)
    const body = mat(color, .26, .35)
    const fender = mat(color, .3, .3)
    softBox(car, trim, 2.12, .3, 4.55, 0, .54, 0)
    softBox(car, body, 2.06, .92, 4.5, 0, 1.02, 0)
    softBox(car, body, 1.98, 1.14, 2.95, 0, 1.95, -.62, .035)
    box(car, glass, 1.76, .78, .025, 0, 2.02, .87)
    box(car, glass, 1.76, .78, .025, 0, 2.02, -2.11)
    // Distinct window panes, pillars and door seams along both sides.
    for (const side of [-1, 1]) {
      const sx = side * 1.002
      box(car, glass, .025, .76, 1.1, sx, 2.02, .23)
      box(car, glass, .025, .76, 1.14, sx, 2.02, -1.05)
      box(car, trim, .05, .88, .085, sx * 1.015, 2.02, -.39)
      box(car, trim, .04, .045, 2.92, sx * 1.02, 1.59, -.62)
      box(car, trim, .025, .72, .016, side * 1.041, 1.13, -.4)
      box(car, trim, .025, .72, .016, side * 1.041, 1.13, -1.7)
      box(car, chrome, .045, .07, .2, side * 1.065, 1.39, -.2)
      box(car, chrome, .045, .07, .2, side * 1.065, 1.39, -1.48)
      softBox(car, body, .3, .22, .4, side * 1.13, 1.78, .62, .035)
      box(car, trim, .31, .08, 2.75, side * 1.08, .52, -.36)
      for (const wz of [-1.45, 1.47]) {
        softBox(car, fender, .28, .24, 1.3, side * 1.035, .97, wz, .055)
        wheel(car, side * 1.045, wz)
      }
    }
    softBox(car, body, 1.98, .17, 1.35, 0, 1.49, 1.48, .035)
    // Raised center bonnet, contrasting grille and round light signatures.
    box(car, trim, .76, .055, .92, 0, 1.594, 1.47)
    softBox(car, trim, 1.13, .54, .055, 0, 1.1, 2.285, .05)
    for (let gx = -.45; gx <= .45; gx += .15) box(car, chrome, .035, .43, .045, gx, 1.1, 2.326)
    for (const sx of [-.77, .77]) {
      const surround = mesh(new THREE.CylinderGeometry(.24, .24, .055, 32), chrome, car, sx, 1.17, 2.29)
      surround.rotation.x = Math.PI / 2
      const lens = mesh(new THREE.CylinderGeometry(.185, .185, .065, 32), headlight, car, sx, 1.17, 2.31)
      lens.rotation.x = Math.PI / 2
      box(car, headlight, .3, .055, .035, sx, 1.45, 2.3)
      box(car, tailLight, .26, .13, .05, sx, 1.12, -2.28)
    }
    softBox(car, trim, 2.12, .34, .27, 0, .68, 2.24, .06)
    box(car, darkChrome, 1.45, .15, .03, 0, .69, 2.395)
    box(car, trim, 2.06, .24, .22, 0, .65, -2.26)
    // Rear spare tire and roof rails carry the recognizable boxy silhouette.
    const spare = mesh(new THREE.CylinderGeometry(.43, .43, .23, 28), trim, car, 0, 1.3, -2.38)
    spare.rotation.x = Math.PI / 2
    for (const sx of [-.8, .8]) box(car, steel, .065, .09, 2.8, sx, 2.57, -.63)
  }

  suv('#dedbc8', -6.9, 2.25, .1)
  suv('#e3e5df', -6.55, -3.1, .08)
  suv('#3c4748', -6.25, -8.4, .06)
  suv('#426351', -6.05, -13.7, .05)

  function coupe(): void {
    const car = new THREE.Group()
    car.position.set(5.05, .01, -.75)
    car.rotation.y = -.12
    scene.add(car)
    const body = mat('#333c42', .24, .55)
    softBox(car, trim, 2.05, .25, 4.9, 0, .42, 0)
    softBox(car, body, 2.13, .61, 4.8, 0, .85, 0, .14)
    softBox(car, body, 1.85, .66, 2.33, 0, 1.37, -.43, .17)
    // Sloped windshield and fastback rear glass.
    const wind = box(car, glass, 1.65, .65, .035, 0, 1.45, .7)
    wind.rotation.x = -.5
    const rear = box(car, glass, 1.62, .6, .035, 0, 1.43, -1.6)
    rear.rotation.x = .6
    for (const side of [-1, 1]) {
      softBox(car, glass, .025, .41, 1.65, side * .936, 1.47, -.45, .01)
      box(car, trim, .045, .46, .07, side * .956, 1.45, -.4)
      softBox(car, body, .22, .17, .31, side * 1.08, 1.26, .5, .04)
      box(car, darkChrome, .035, .045, .19, side * 1.084, 1.13, -.23)
      box(car, trim, .12, .12, 2.7, side * 1.04, .36, -.12)
      for (const wz of [-1.53, 1.49]) {
        softBox(car, body, .13, .17, 1.1, side * 1.057, .93, wz, .04)
        wheel(car, side * 1.035, wz, .91, true)
      }
    }
    softBox(car, body, 1.99, .1, 1.47, 0, 1.18, 1.46, .035)
    box(car, trim, .68, .055, .52, 0, 1.256, 1.24)
    softBox(car, trim, 1.98, .3, .065, 0, .96, 2.407, .05)
    box(car, trim, 1.76, .17, .1, 0, .57, 2.42)
    for (let gx = -.8; gx < .9; gx += .11) box(car, darkChrome, .025, .15, .02, gx, .91, 2.454)
    for (const sx of [-.73, .73]) {
      softBox(car, headlight, .48, .1, .035, sx, 1.06, 2.452, .02)
      box(car, tailLight, .56, .08, .04, sx, 1.02, -2.42)
      box(car, headlight, .33, .035, .035, sx, .61, 2.48)
    }
    box(car, trim, 1.86, .06, .26, 0, 1.16, -2.12)
  }
  coupe()

  function pickup(): void {
    const car = new THREE.Group()
    car.position.set(2.3, .01, -12.4)
    car.rotation.y = -.07
    scene.add(car)
    const orange = mat('#bd6230', .32, .36)
    softBox(car, trim, 2.23, .35, 5.3, 0, .57, 0)
    softBox(car, orange, 2.19, .8, 5.16, 0, 1.12, 0)
    softBox(car, orange, 2.05, 1.02, 2.5, 0, 1.98, .03, .05)
    box(car, glass, 1.83, .72, .04, 0, 2.01, 1.3)
    for (const side of [-1, 1]) {
      box(car, glass, .03, .72, 1.01, side * 1.038, 2.01, .67)
      box(car, glass, .03, .72, .98, side * 1.038, 2.01, -.51)
      softBox(car, trim, .3, .23, .4, side * 1.2, 1.85, .9, .03)
      box(car, trim, .07, .88, .08, side * 1.055, 1.99, .08)
      box(car, trim, .2, .12, 2.55, side * 1.13, .58, .1)
      box(car, trim, .045, .07, .22, side * 1.116, 1.43, .3)
      box(car, orange, .16, .3, 1.2, side * 1.08, 1.04, 1.68)
      for (const wz of [-1.72, 1.7]) wheel(car, side * 1.13, wz, 1.12, true)
    }
    box(car, trim, 1.86, .12, 1.23, 0, 1.51, -1.92)
    softBox(car, orange, 2.08, .12, 1.25, 0, 1.57, 1.93, .03)
    softBox(car, trim, 2.04, .61, .08, 0, 1.14, 2.63, .04)
    for (let gx = -.7; gx <= .7; gx += .2) box(car, darkChrome, .09, .36, .04, gx, 1.17, 2.685)
    for (const sx of [-.85, .85]) box(car, headlight, .24, .2, .05, sx, 1.27, 2.7)
    box(car, trim, 2.25, .28, .29, 0, .71, 2.55)
    box(car, darkChrome, .82, .14, .06, 0, .72, 2.72)
  }
  pickup()

  // Outdoor context: a quiet parking court, low curb, and a soft tree line.
  const line = mat('#c6c4b5', .95)
  for (let z = -25; z <= 8; z += 5.2) box(scene, line, 5.9, .015, .09, 15.7, -.12, z)
  box(scene, mat('#b7b8aa', .95), .24, .25, 72, 25, -.03, -14)
  const leaves = [mat('#436246', .97), mat('#567449', .98), mat('#66814d', 1), mat('#385a43', .97)]
  const trunk = mat('#695e4b', .98)
  for (let i = 0; i < 34; i++) {
    const x = i < 17 ? -24 + i * 3.5 : 27 + random() * 8
    const z = i < 17 ? -35 - random() * 5 : -30 + (i - 17) * 3.8
    const h = 5.3 + random() * 3
    mesh(new THREE.CylinderGeometry(.15, .24, h * .65, 6), trunk, scene, x, h * .3, z)
    for (let crown = 0; crown < 3; crown++) {
      const foliage = mesh(new THREE.IcosahedronGeometry(1.7 + random() * 1.2, 1), leaves[(i + crown) % leaves.length], scene,
        x + (random() - .5) * 1.8, h * .65 + random() * 1.3, z + (random() - .5) * 1.8)
      foliage.scale.y = 1.25
      foliage.castShadow = false
    }
  }

  // The authored room keeps the walking area clear down its central aisle.
  scene.userData.bounds = { minX: -9.2, maxX: 9.1, minZ: -17.8, maxZ: 8 }
  return scene
}
