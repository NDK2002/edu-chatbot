-- Migration 003: add steps column to messages for rule_engine responses

alter table messages add column steps jsonb;
