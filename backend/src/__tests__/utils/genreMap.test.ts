import { normalizeGenre } from "../../utils/genreMap";

describe("normalizeGenre", () => {
    it("maps hip hop genres correctly", () => {
        expect(normalizeGenre("hip hop")).toBe("Hip Hop");
        expect(normalizeGenre("dark trap")).toBe("Hip Hop");
        expect(normalizeGenre("underground rap")).toBe("Hip Hop");
        expect(normalizeGenre("uk drill")).toBe("Hip Hop");
    });

    it("maps r&b genres correctly", () => {
        expect(normalizeGenre("r&b")).toBe("R&B");
        expect(normalizeGenre("neo soul")).toBe("R&B");
        expect(normalizeGenre("contemporary r&b")).toBe("R&B");
    });

    it("maps electronic genres correctly", () => {
        expect(normalizeGenre("vapor twitch")).toBe("Electronic");
        expect(normalizeGenre("deep house")).toBe("Electronic");
        expect(normalizeGenre("lo-fi beats")).toBe("Electronic");
        expect(normalizeGenre("drum and bass")).toBe("Electronic");
    });

    it("maps indie genres correctly", () => {
        expect(normalizeGenre("indie pop")).toBe("Indie");
        expect(normalizeGenre("bedroom pop")).toBe("Indie");
        expect(normalizeGenre("shoegaze")).toBe("Indie");
    });

    it("maps metal before rock", () => {
        expect(normalizeGenre("death metal")).toBe("Metal");
        expect(normalizeGenre("black metal")).toBe("Metal");
        expect(normalizeGenre("metalcore")).toBe("Metal");
    });

    it("maps rock genres correctly", () => {
        expect(normalizeGenre("classic rock")).toBe("Rock");
        expect(normalizeGenre("grunge")).toBe("Rock");
    });

    it("maps pop genres correctly", () => {
        expect(normalizeGenre("dance pop")).toBe("Pop");
        expect(normalizeGenre("k-pop")).toBe("Pop");
    });

    it("maps latin genres correctly", () => {
        expect(normalizeGenre("reggaeton")).toBe("Latin");
        expect(normalizeGenre("latin pop")).toBe("Latin");
    });

    it("maps folk correctly", () => {
        expect(normalizeGenre("folk")).toBe("Folk");
        expect(normalizeGenre("singer-songwriter")).toBe("Folk");
    });

    it("returns Other for unknown genres", () => {
        expect(normalizeGenre("unknown genre xyz")).toBe("Other");
        expect(normalizeGenre("")).toBe("Other");
    });

    it("is case-insensitive", () => {
        expect(normalizeGenre("HIP HOP")).toBe("Hip Hop");
        expect(normalizeGenre("TRAP")).toBe("Hip Hop");
    });
});
