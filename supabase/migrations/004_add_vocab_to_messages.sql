-- Migration 004: add vocab column to messages for dictionary responses

alter table messages add column vocab jsonb;
