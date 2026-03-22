"use client";

import { useEffect, useState } from "react";
import { api } from "@/lib/api";
import type { PlaceDetail, PlaceSearchResult, PlaceSummary } from "@/lib/types";

type ManualPlaceForm = {
  name: string;
  lat: string;
  lng: string;
  category: string;
  tags: string;
  traits: string;
};

export default function PlacesPage() {
  const [places, setPlaces] = useState<PlaceSummary[]>([]);
  const [searchText, setSearchText] = useState("");
  const [searchResults, setSearchResults] = useState<PlaceSearchResult[]>([]);
  const [manualForm, setManualForm] = useState<ManualPlaceForm>({
    name: "",
    lat: "",
    lng: "",
    category: "",
    tags: "",
    traits: "",
  });
  const [selectedPlace, setSelectedPlace] = useState<PlaceDetail | null>(null);
  const [message, setMessage] = useState<string | null>(null);
  const [error, setError] = useState<string | null>(null);

  async function loadPlaces() {
    try {
      const response = await api<{ items: PlaceSummary[] }>("/api/places");
      setPlaces(response.items);
    } catch (loadError) {
      setError(loadError instanceof Error ? loadError.message : "場所一覧の取得に失敗しました。");
    }
  }

  useEffect(() => {
    void loadPlaces();
  }, []);

  async function openPlace(placeId: number) {
    try {
      const detail = await api<PlaceDetail>(`/api/places/${placeId}`);
      setSelectedPlace(detail);
      setError(null);
    } catch (loadError) {
      setError(loadError instanceof Error ? loadError.message : "場所詳細の取得に失敗しました。");
    }
  }

  async function searchProvider() {
    try {
      const response = await api<{ results: PlaceSearchResult[] }>("/api/places/search-text", {
        method: "POST",
        body: JSON.stringify({ query: searchText, region: "jp" }),
      });
      setSearchResults(response.results);
      setError(null);
    } catch (searchError) {
      setError(searchError instanceof Error ? searchError.message : "検索に失敗しました。");
    }
  }

  async function importPlace(result: PlaceSearchResult) {
    try {
      await api<PlaceDetail>("/api/places/import", {
        method: "POST",
        body: JSON.stringify({
          provider: result.provider,
          provider_place_id: result.provider_place_id,
          overrides: {},
        }),
      });
      await loadPlaces();
      setMessage("場所を取り込みました。");
      setError(null);
    } catch (importError) {
      setError(importError instanceof Error ? importError.message : "取り込みに失敗しました。");
    }
  }

  async function createManualPlace() {
    try {
      await api<PlaceDetail>("/api/places", {
        method: "POST",
        body: JSON.stringify({
          name: manualForm.name,
          lat: Number(manualForm.lat),
          lng: Number(manualForm.lng),
          category: manualForm.category || null,
          tags: manualForm.tags ? manualForm.tags.split(",").map((value) => value.trim()).filter(Boolean) : [],
          traits: manualForm.traits ? manualForm.traits.split(",").map((value) => value.trim()).filter(Boolean) : [],
          visit_profile: {
            stay_min_minutes: 20,
            stay_preferred_minutes: 45,
            stay_max_minutes: 90,
          },
          availability_rules: [{ open_minute: 0, close_minute: 1440, closed_flag: false }],
        }),
      });
      setManualForm({ name: "", lat: "", lng: "", category: "", tags: "", traits: "" });
      await loadPlaces();
      setMessage("手動場所を作成しました。");
      setError(null);
    } catch (createError) {
      setError(createError instanceof Error ? createError.message : "手動作成に失敗しました。");
    }
  }

  return (
    <main className="page-shell">
      <div className="page-frame stack">
        <section className="hero-panel">
          <div className="section-heading">
            <span className="eyebrow">Places</span>
            <h1>場所ライブラリ</h1>
            <p>テキスト検索、取り込み、手動作成、詳細確認をまとめて行えます。</p>
          </div>
        </section>
        {message ? <p className="success-text">{message}</p> : null}
        {error ? <p className="error-text">{error}</p> : null}
        <div className="two-column">
          <section className="panel">
            <div className="section-heading">
              <h2>ローカル場所</h2>
              <p>保存済みの場所一覧です。</p>
            </div>
            <div className="stack">
              {places.map((place) => (
                <article key={place.id} className="candidate-card">
                  <div>
                    <div className="candidate-title">{place.name}</div>
                    <div className="candidate-meta">
                      {place.category ?? "未分類"} / {place.tags.join(", ") || "タグなし"}
                    </div>
                  </div>
                  <button className="small-button" type="button" onClick={() => void openPlace(place.id)}>
                    詳細
                  </button>
                </article>
              ))}
            </div>
          </section>
          <section className="panel">
            <div className="section-heading">
              <h2>検索と作成</h2>
              <p>外部検索と手動作成の両方に対応しています。</p>
            </div>
            <div className="button-row">
              <input value={searchText} onChange={(event) => setSearchText(event.target.value)} placeholder="テキスト検索" />
              <button className="primary-button" type="button" onClick={() => void searchProvider()}>
                検索
              </button>
            </div>
            <div className="stack">
              {searchResults.map((result) => (
                <article key={result.provider_place_id} className="candidate-card">
                  <div>
                    <div className="candidate-title">{result.name}</div>
                    <div className="candidate-meta">{result.primary_type ?? "unknown"}</div>
                  </div>
                  <button className="small-button" type="button" onClick={() => void importPlace(result)}>
                    取り込む
                  </button>
                </article>
              ))}
            </div>
            <div className="field-grid">
              <label className="field">
                <span>名前</span>
                <input value={manualForm.name} onChange={(event) => setManualForm((current) => ({ ...current, name: event.target.value }))} />
              </label>
              <label className="field">
                <span>緯度</span>
                <input value={manualForm.lat} onChange={(event) => setManualForm((current) => ({ ...current, lat: event.target.value }))} />
              </label>
              <label className="field">
                <span>経度</span>
                <input value={manualForm.lng} onChange={(event) => setManualForm((current) => ({ ...current, lng: event.target.value }))} />
              </label>
              <label className="field">
                <span>カテゴリ</span>
                <input value={manualForm.category} onChange={(event) => setManualForm((current) => ({ ...current, category: event.target.value }))} />
              </label>
              <label className="field">
                <span>タグ (comma)</span>
                <input value={manualForm.tags} onChange={(event) => setManualForm((current) => ({ ...current, tags: event.target.value }))} />
              </label>
              <label className="field">
                <span>traits (comma)</span>
                <input value={manualForm.traits} onChange={(event) => setManualForm((current) => ({ ...current, traits: event.target.value }))} />
              </label>
            </div>
            <button className="primary-button" type="button" onClick={() => void createManualPlace()}>
              手動場所を作成
            </button>
          </section>
        </div>
        <section className="panel">
          <div className="section-heading">
            <h2>詳細</h2>
            <p>選択中の場所の詳細です。</p>
          </div>
          {selectedPlace ? (
            <div className="stack">
              <div className="candidate-title">{selectedPlace.name}</div>
              <div className="candidate-meta">{selectedPlace.category ?? "未分類"}</div>
              <div className="candidate-meta">{selectedPlace.tags.join(", ") || "タグなし"}</div>
            </div>
          ) : (
            <div className="empty-card">一覧から場所を選択してください。</div>
          )}
        </section>
      </div>
    </main>
  );
}
