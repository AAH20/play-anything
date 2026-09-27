/** Detach before Sigma.kill(): it deliberately loses its old WebGL contexts. */
export function bindRendererContextEvents(
  canvases: Iterable<EventTarget>,
  onLost: (event: Event) => void,
  onRestored: () => void,
) {
  let disposed = false;
  const targets = [...canvases];
  const lost = (event: Event) => { if (!disposed) onLost(event); };
  const restored = () => { if (!disposed) onRestored(); };
  for (const target of targets) {
    target.addEventListener('webglcontextlost', lost);
    target.addEventListener('webglcontextrestored', restored);
  }
  return () => {
    disposed = true;
    for (const target of targets) {
      target.removeEventListener('webglcontextlost', lost);
      target.removeEventListener('webglcontextrestored', restored);
    }
  };
}
