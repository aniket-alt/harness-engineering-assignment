// Pure dice logic, kept free of harness imports so it can be unit-tested.
export function rollDie(sides = 6, rng = Math.random) {
  if (!Number.isInteger(sides) || sides < 2 || sides > 1000) {
    throw new Error(`sides must be an integer between 2 and 1000, got ${sides}`)
  }
  return Math.floor(rng() * sides) + 1
}
