/**
 * HTML Utility Tests
 */

import * as assert from "assert";
import { escapeHtml } from "../utils/html";

describe("escapeHtml", () => {
    it("should escape ampersand", () => {
        // Arrange
        const input = "foo & bar";

        // Act
        const result = escapeHtml(input);

        // Assert
        assert.strictEqual(result, "foo &amp; bar");
    });

    it("should escape less than sign", () => {
        // Arrange
        const input = "a < b";

        // Act
        const result = escapeHtml(input);

        // Assert
        assert.strictEqual(result, "a &lt; b");
    });

    it("should escape greater than sign", () => {
        // Arrange
        const input = "a > b";

        // Act
        const result = escapeHtml(input);

        // Assert
        assert.strictEqual(result, "a &gt; b");
    });

    it("should escape double quotes", () => {
        // Arrange
        const input = 'say "hello"';

        // Act
        const result = escapeHtml(input);

        // Assert
        assert.strictEqual(result, "say &quot;hello&quot;");
    });

    it("should escape single quotes", () => {
        // Arrange
        const input = "it's";

        // Act
        const result = escapeHtml(input);

        // Assert
        assert.strictEqual(result, "it&#039;s");
    });

    it("should handle multiple special characters", () => {
        // Arrange
        const input = '<script>alert("XSS & attack")</script>';

        // Act
        const result = escapeHtml(input);

        // Assert
        assert.strictEqual(
            result,
            "&lt;script&gt;alert(&quot;XSS &amp; attack&quot;)&lt;/script&gt;"
        );
    });

    it("should return empty string for empty input", () => {
        // Arrange
        const input = "";

        // Act
        const result = escapeHtml(input);

        // Assert
        assert.strictEqual(result, "");
    });

    it("should return unchanged string when no special characters", () => {
        // Arrange
        const input = "Hello World 123";

        // Act
        const result = escapeHtml(input);

        // Assert
        assert.strictEqual(result, "Hello World 123");
    });

    it("should handle Japanese text correctly", () => {
        // Arrange
        const input = "日本語テスト<script>";

        // Act
        const result = escapeHtml(input);

        // Assert
        assert.strictEqual(result, "日本語テスト&lt;script&gt;");
    });
});
