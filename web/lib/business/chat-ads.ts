import { and, desc, eq } from "drizzle-orm";
import { getDb } from "@/lib/db/client";
import { chatAds } from "@/lib/db/schema";
import { NotFoundError, ValidationError } from "@/lib/business/bots";

// Publicidad de un chat -- ver el comentario de chatAds en lib/db/schema.ts
// para el diseño general. Regla central de este archivo: como máximo 4 filas
// "published" por chat_config_id, cola FILO (la más nueva por publishedAt
// entra, la más vieja sale) -- exactamente la misma lógica sin importar si
// quien publica es el admin/PRO desde la UI (por `id`) o un sistema externo
// vía bot-key (por `externalRef`, ver lib/auth/bot-key.ts).

const PUBLISHED_LIMIT = 4;

type ChatAdRow = typeof chatAds.$inferSelect;

function toAdDto(row: ChatAdRow) {
  return {
    id: row.id,
    chat_config_id: row.chatConfigId,
    external_ref: row.externalRef,
    title: row.title,
    description: row.description,
    image_url: row.imageUrl,
    link_url: row.linkUrl,
    published: row.published,
    published_at: row.publishedAt,
    created_at: row.createdAt,
    updated_at: row.updatedAt,
  };
}

// Subset público para el widget de chat -- ver lib/business/chats.ts::toPublicConfigDto.
function toPublicAdDto(row: ChatAdRow) {
  return {
    id: row.id,
    external_ref: row.externalRef,
    title: row.title,
    description: row.description,
    image_url: row.imageUrl,
    link_url: row.linkUrl,
    published_at: row.publishedAt,
  };
}

export interface ChatAdInput {
  title?: string;
  description?: string;
  imageUrl: string;
  linkUrl?: string;
}

function validateAdInput(input: ChatAdInput) {
  if (!input.imageUrl?.trim()) throw new ValidationError("image_url es requerido");
}

async function getAdRow(chatConfigId: string, adId: string): Promise<ChatAdRow | null> {
  const db = getDb();
  const [row] = await db
    .select()
    .from(chatAds)
    .where(and(eq(chatAds.id, adId), eq(chatAds.chatConfigId, chatConfigId)));
  return row ?? null;
}

// Ordenadas nueva-primero, coherente con "insertando arriba" (más nueva
// publicada primero) -- getPublishedAds abajo usa el mismo orden.
export async function listAds(chatConfigId: string) {
  const db = getDb();
  const rows = await db
    .select()
    .from(chatAds)
    .where(eq(chatAds.chatConfigId, chatConfigId))
    .orderBy(desc(chatAds.createdAt));
  return rows.map(toAdDto);
}

export async function createAd(chatConfigId: string, input: ChatAdInput) {
  validateAdInput(input);
  const db = getDb();
  const id = crypto.randomUUID();
  await db.insert(chatAds).values({
    id,
    chatConfigId,
    title: input.title?.trim() || null,
    description: input.description?.trim() || null,
    imageUrl: input.imageUrl.trim(),
    linkUrl: input.linkUrl?.trim() || null,
  });
  return toAdDto((await getAdRow(chatConfigId, id))!);
}

export async function updateAd(chatConfigId: string, adId: string, input: ChatAdInput) {
  validateAdInput(input);
  const existing = await getAdRow(chatConfigId, adId);
  if (!existing) throw new NotFoundError(`Publicidad no encontrada: ${adId}`);
  const db = getDb();
  await db
    .update(chatAds)
    .set({
      title: input.title?.trim() || null,
      description: input.description?.trim() || null,
      imageUrl: input.imageUrl.trim(),
      linkUrl: input.linkUrl?.trim() || null,
      updatedAt: new Date(),
    })
    .where(eq(chatAds.id, adId));
  return toAdDto((await getAdRow(chatConfigId, adId))!);
}

export async function deleteAd(chatConfigId: string, adId: string): Promise<void> {
  const existing = await getAdRow(chatConfigId, adId);
  if (!existing) throw new NotFoundError(`Publicidad no encontrada: ${adId}`);
  const db = getDb();
  await db.delete(chatAds).where(eq(chatAds.id, adId));
}

// Despublica el excedente por encima de PUBLISHED_LIMIT, la(s) más vieja(s)
// por publishedAt -- llamado siempre DESPUÉS de marcar una fila published=true.
// Sin db.transaction: el driver neon-http de esta app no soporta
// transacciones interactivas (ver lib/db/client.ts) y ningún otro archivo de
// lib/business/*.ts las usa -- mismo criterio aceptado que el resto del repo.
async function evictExcess(chatConfigId: string): Promise<void> {
  const db = getDb();
  const published = await db
    .select({ id: chatAds.id })
    .from(chatAds)
    .where(and(eq(chatAds.chatConfigId, chatConfigId), eq(chatAds.published, true)))
    .orderBy(desc(chatAds.publishedAt));
  const excess = published.slice(PUBLISHED_LIMIT);
  for (const row of excess) {
    await db.update(chatAds).set({ published: false, updatedAt: new Date() }).where(eq(chatAds.id, row.id));
  }
}

// ─── Gestión (admin/PRO, por `id` interno) ─────────────────────────────

export async function setAdPublished(chatConfigId: string, adId: string, published: boolean) {
  const existing = await getAdRow(chatConfigId, adId);
  if (!existing) throw new NotFoundError(`Publicidad no encontrada: ${adId}`);
  const db = getDb();
  await db
    .update(chatAds)
    .set({ published, publishedAt: published ? new Date() : existing.publishedAt, updatedAt: new Date() })
    .where(eq(chatAds.id, adId));
  if (published) await evictExcess(chatConfigId);
  return toAdDto((await getAdRow(chatConfigId, adId))!);
}

// ─── Runtime (bot-key externo, por `externalRef`) ──────────────────────

export interface PublishAdInput {
  externalRef?: string;
  title?: string;
  description?: string;
  imageUrl: string;
  linkUrl?: string;
}

// Upsert-por-externalRef si viene, si no siempre inserta una fila nueva --
// después publica + evict, y devuelve el set activo (máx 4, nueva-primero)
// para que el caller pueda diffear contra lo que mandó y saber si su propia
// publicidad quedó afuera.
export async function publishAd(chatConfigId: string, input: PublishAdInput) {
  validateAdInput(input);
  const db = getDb();

  let id: string | null = null;
  if (input.externalRef) {
    const [existing] = await db
      .select({ id: chatAds.id })
      .from(chatAds)
      .where(and(eq(chatAds.chatConfigId, chatConfigId), eq(chatAds.externalRef, input.externalRef)));
    id = existing?.id ?? null;
  }

  if (id) {
    await db
      .update(chatAds)
      .set({
        title: input.title?.trim() || null,
        description: input.description?.trim() || null,
        imageUrl: input.imageUrl.trim(),
        linkUrl: input.linkUrl?.trim() || null,
        published: true,
        publishedAt: new Date(),
        updatedAt: new Date(),
      })
      .where(eq(chatAds.id, id));
  } else {
    id = crypto.randomUUID();
    await db.insert(chatAds).values({
      id,
      chatConfigId,
      externalRef: input.externalRef ?? null,
      title: input.title?.trim() || null,
      description: input.description?.trim() || null,
      imageUrl: input.imageUrl.trim(),
      linkUrl: input.linkUrl?.trim() || null,
      published: true,
      publishedAt: new Date(),
    });
  }

  await evictExcess(chatConfigId);
  return getPublishedAds(chatConfigId);
}

// No-op (no 500) si no hay fila con ese externalRef -- el caller externo
// puede llamar unpublish sin haber sincronizado antes, no es un error.
export async function unpublishAd(chatConfigId: string, externalRef: string) {
  const db = getDb();
  await db
    .update(chatAds)
    .set({ published: false, updatedAt: new Date() })
    .where(and(eq(chatAds.chatConfigId, chatConfigId), eq(chatAds.externalRef, externalRef)));
  return getPublishedAds(chatConfigId);
}

// ─── Lectura pública (widget de chat) ──────────────────────────────────

export async function getPublishedAds(chatConfigId: string) {
  const db = getDb();
  const rows = await db
    .select()
    .from(chatAds)
    .where(and(eq(chatAds.chatConfigId, chatConfigId), eq(chatAds.published, true)))
    .orderBy(desc(chatAds.publishedAt))
    .limit(PUBLISHED_LIMIT);
  return rows.map(toPublicAdDto);
}
