/**
 * Grid de atractores del editor de flows.
 *
 * El tamaño de la celda es un octavo del ancho del chip de un nodo (NODE_WIDTH,
 * definido junto al resto de las constantes de layout de nodo en flowStore.js).
 * Todo movimiento en el canvas — arrastre de nodos y de bend points de edges —
 * se cuantiza a esta grilla.
 */
export const NODE_WIDTH = 160
export const GRID_SIZE = NODE_WIDTH / 8 // 20

export function snapValue(value, gridSize = GRID_SIZE) {
  return Math.round(value / gridSize) * gridSize || 0 // evita -0
}

export function snapPoint(point, gridSize = GRID_SIZE) {
  return { x: snapValue(point.x, gridSize), y: snapValue(point.y, gridSize) }
}
