export const clamp = (x,a,b)=>Math.max(a,Math.min(b,x));

export function rectRel(node, rootRect){
  const r = node.getBoundingClientRect();
  return { left:r.left-rootRect.left, right:r.right-rootRect.left,
           top:r.top-rootRect.top,     bottom:r.bottom-rootRect.top };
}
export const midX = r => (r.left + r.right)/2;
