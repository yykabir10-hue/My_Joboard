import { describe, expect, test } from "bun:test"
import { runCLI } from "./helpers"

function parsedStderr(stderr: string): { error?: string; code?: string } {
  try {
    return JSON.parse(stderr)
  } catch {
    return {}
  }
}

describe("Arbeitsagentur CLI flag validation", () => {
  describe("numeric flag validation", () => {
    for (const flag of ["jobage", "page", "limit", "size", "radius"]) {
      test(`--${flag} with a non-numeric value exits 1 with BAD_ARG`, async () => {
        const result = await runCLI(["search", `--${flag}`, "foo"])
        expect(result.exitCode).not.toBe(0)
        const err = parsedStderr(result.stderr)
        expect(err.code).toBe("BAD_ARG")
        expect(err.error).toMatch(new RegExp(flag))
      })
    }

    test("--jobage 0 is accepted (falsy int must not be treated as missing)", async () => {
      const result = await runCLI(["search", "--jobage", "0", "--limit", "1"])
      expect(parsedStderr(result.stderr).code).not.toBe("BAD_ARG")
    })
  })

  describe("--size bounds (API page-size limit is 100)", () => {
    test("size above 100 is rejected", async () => {
      const result = await runCLI(["search", "--size", "500"])
      expect(result.exitCode).not.toBe(0)
      expect(parsedStderr(result.stderr).code).toBe("BAD_ARG")
    })

    test("size below 1 is rejected", async () => {
      const result = await runCLI(["search", "--size", "0"])
      expect(result.exitCode).not.toBe(0)
      expect(parsedStderr(result.stderr).code).toBe("BAD_ARG")
    })
  })

  describe("detail", () => {
    test("missing <referenznummer|url> exits 1 with NO_ID", async () => {
      const result = await runCLI(["detail"])
      expect(result.exitCode).not.toBe(0)
      expect(parsedStderr(result.stderr).code).toBe("NO_ID")
    })

    test("a reference number with no detail record exits 1 with NOT_FOUND, not a crash", async () => {
      const result = await runCLI(["detail", "00000-0000000000-X"])
      expect(result.exitCode).not.toBe(0)
      expect(parsedStderr(result.stderr).code).toBe("NOT_FOUND")
    })
  })

  describe("unknown command", () => {
    test("exits 1 with BAD_CMD", async () => {
      const result = await runCLI(["bogus"])
      expect(result.exitCode).not.toBe(0)
      expect(parsedStderr(result.stderr).code).toBe("BAD_CMD")
    })
  })
})
