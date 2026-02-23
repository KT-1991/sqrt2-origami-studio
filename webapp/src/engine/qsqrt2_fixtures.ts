import {
  ANGLE_COUNT,
  DIRS,
  HALF,
  INV_SQRT2,
  ONE,
  SQRT2_MINUS_ONE,
  add,
  div,
  fromDyadic,
  fromInt,
  mirroredDirIdx,
  mul,
  q2Cmp,
  qsqrt2Approx,
} from "./qsqrt2";

function assert(condition: boolean, message: string): void {
  if (!condition) {
    throw new Error(message);
  }
}

function near(a: number, b: number, tol: number, message: string): void {
  if (Math.abs(a - b) > tol) {
    throw new Error(`${message}: got=${a}, expected=${b}, tol=${tol}`);
  }
}

export function runQsqrt2Fixture(): void {
  const oneFromHalf = add(HALF, HALF);
  assert(q2Cmp(oneFromHalf, ONE) === 0, "HALF + HALF must equal ONE");

  const oneFromQuarter = mul(fromDyadic(1, 2), fromInt(4));
  assert(q2Cmp(oneFromQuarter, ONE) === 0, "quarter * 4 must equal ONE");

  const sq = mul(SQRT2_MINUS_ONE, SQRT2_MINUS_ONE);
  assert(sq.a === 3n && sq.b === -2n && sq.k === 0, "(sqrt2-1)^2 exact mismatch");

  const two = div(fromInt(1), HALF);
  assert(q2Cmp(two, fromInt(2)) === 0, "ONE / HALF must equal 2");

  near(qsqrt2Approx(INV_SQRT2), Math.SQRT1_2, 1e-12, "INV_SQRT2 approx mismatch");

  assert(ANGLE_COUNT === 16, "ANGLE_COUNT must be 16");
  assert(DIRS.length === 16, "DIRS length must be 16");
  assert(mirroredDirIdx(1) === 3, "mirroredDirIdx(1) must be 3");
}

