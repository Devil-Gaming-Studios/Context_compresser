import { useEffect, useRef } from 'react'

export default function Background() {
  const orb1 = useRef(null)
  const orb2 = useRef(null)
  const orb3 = useRef(null)

  useEffect(() => {
    let rafId = null
    let pendingX = 0
    let pendingY = 0

    const applyTransform = () => {
      rafId = null
      if (orb1.current) orb1.current.style.transform = `translate(${pendingX}px, ${pendingY}px)`
      if (orb2.current) orb2.current.style.transform = `translate(${-pendingX * 0.8}px, ${-pendingY * 0.8}px)`
      if (orb3.current) orb3.current.style.transform = `translate(${pendingX * 0.5}px, ${pendingY * 0.5}px)`
    }

    const onMouseMove = (e) => {
      pendingX = (e.clientX / window.innerWidth - 0.5) * 20
      pendingY = (e.clientY / window.innerHeight - 0.5) * 20
      if (rafId === null) rafId = requestAnimationFrame(applyTransform)
    }
    window.addEventListener('mousemove', onMouseMove, { passive: true })
    return () => {
      window.removeEventListener('mousemove', onMouseMove)
      if (rafId !== null) cancelAnimationFrame(rafId)
    }
  }, [])

  return (
    <div className="app-background">
      <div className="bg-grid" />
      <div className="bg-noise" />
      <div ref={orb1} className="bg-orb bg-orb-1" />
      <div ref={orb2} className="bg-orb bg-orb-2" />
      <div ref={orb3} className="bg-orb bg-orb-3" />
    </div>
  )
}