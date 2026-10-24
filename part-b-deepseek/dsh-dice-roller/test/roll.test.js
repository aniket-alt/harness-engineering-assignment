import assert from 'node:assert/strict'
import { test } from 'node:test'
import { rollDie } from '../roll.js'

test('rng extremes map to 1 and the top face', () => {
  assert.equal(rollDie(6, () => 0), 1)
  assert.equal(rollDie(6, () => 0.999999), 6)
})

test('every result over many rolls is within range', () => {
  for (let i = 0; i < 5000; i++) {
    const n = rollDie(6)
    assert.ok(Number.isInteger(n) && n >= 1 && n <= 6)
  }
})

test('invalid side counts are rejected', () => {
  for (const bad of [1, 0, -3, 2.5, 1001, NaN]) assert.throws(() => rollDie(bad), /sides must be/)
})
