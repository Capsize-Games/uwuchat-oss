/**
 * Normalize an avatar_image value to a valid <img> src attribute.
 *
 * avatar_image in the database can be:
 *   - null / undefined / "" → no avatar
 *   - An HTTPS URL (e.g., from Steam OAuth import) → use directly
 *   - Raw base64 (from the image uploader) → wrap in a data: URI
 */
export function getAvatarSrc(
    avatarImage: string | null | undefined,
): string | null {
    if (!avatarImage) return null;
    if (
        avatarImage.startsWith("http://") ||
        avatarImage.startsWith("https://")
    ) {
        return avatarImage;
    }
    return `data:image/png;base64,${avatarImage}`;
}
