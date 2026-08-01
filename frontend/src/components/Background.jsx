import { useEffect, useRef } from 'react'

export default function Background() {
  const orb1 = useRef(null)
  const orb2 = useRef(null)
  const orb3 = useRef(null)

  useEffect(() => {
    const onMouseMove = (e) => {
      const x = (e.clientX / window.innerWidth - 0.5) * 20
      const y = (e.clientY / window.innerHeight - 0.5) * 20
      if (orb1.current) orb1.current.style.transform = `translate(${x}px, ${y}px)`
      if (orb2.current) orb2.current.style.transform = `translate(${-x * 0.8}px, ${-y * 0.8}px)`
      if (orb3.current) orb3.current.style.transform = `translate(${x * 0.5}px, ${y * 0.5}px)`
    }
    window.addEventListener('mousemove', onMouseMove, { passive: true })
    return () => window.removeEventListener('mousemove', onMouseMove)
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
