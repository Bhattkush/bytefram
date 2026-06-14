export interface SoilInput {
  N?: number;
  P?: number;
  K?: number;
  pH?: number;
  Organic_Carbon?: number;
}

export interface SmartRecommendRequest {
  lat: number;
  lon: number;
  land_size?: number;
  season?: string;
  soil?: SoilInput;
  irrigated?: boolean;
  profit_mode?: boolean;
  top_n?: number;
  user_id?: string;
}

export interface RiskDetail {
  overall: string;
  risk_score: number;
  drought_risk: string;
  heat_risk: string;
  frost_risk: string;
  flood_risk: string;
  soil_risk: string;
  ndvi_risk: string;
  off_season_risk: string;
  yield_confidence: number;
  confidence_level: string;
}

export interface ExplanationDetail {
  headline: string;
  farmer_tip: string;
  factors: string[];
  key_limiting_factor: string;
  confidence_level: string;
  soil_score: number;
  ndvi_impact: string;
}

export interface RecommendationItem {
  crop: string;
  crop_name: string;
  category: string;
  suitability: number;
  suitability_score: number;
  yield_per_hectare: number;
  total_yield_tonnes: number;
  display_yield: string;
  production_level: string;
  market_price_per_tonne?: number;
  estimated_profit_inr?: number;
  display_profit?: string;
  profit_confidence?: string;
  composite_score?: number;
  risk?: RiskDetail;
  risk_confidence: string;
  explanation?: ExplanationDetail;
  reason: string;
}

export interface RecommendSummary {
  best_crop: string;
  expected_yield: string;
  suitability: string;
  overall_risk: string;
  display_profit: string;
}

export interface AlertItem {
  severity: string;
  icon: string;
  title: string;
  action: string;
}

export interface SmartRecommendResponse {
  status: string;
  location?: string;
  district?: string;
  season?: string;
  land_area_hectares?: number;
  irrigated?: boolean;
  mode?: string;
  input_coordinates?: { lat: number; lon: number };
  location_warning?: string;
  summary?: RecommendSummary;
  one_line_decision?: string;
  confidence?: number;
  insight?: string;
  advice?: string;
  recommendations: RecommendationItem[];
  avoid_crops: unknown[];
  crops_evaluated: number;
  alerts: AlertItem[];
  risk_alerts: AlertItem[];
  weather_summary?: Record<string, unknown>;
  weather_source?: string;
  live_conditions?: string;
}

export interface YieldPredictionRequest {
  district: string;
  season: string;
  year: number;
  crop: string;
  temperature_avg: number;
  temperature_min: number;
  temperature_max: number;
  rainfall: number;
  humidity: number;
  n?: number;
  p?: number;
  k?: number;
  ph?: number;
  organic_carbon?: number;
  ndvi_peak?: number;
}

export interface YieldPredictionResponse {
  crop: string;
  district: string;
  season: string;
  predicted_yield_ton_per_hectare: number;
}

export interface WeatherAlertRequest {
  latitude: number;
  longitude: number;
  district?: string;
}

export interface WeatherAlertResponse {
  latitude: number;
  longitude: number;
  current: Record<string, unknown>;
  alerts: Array<{ type: string; message: string; severity: string }>;
}

export interface UserProfile {
  user_id: string;
  name: string;
  phone_or_email: string;
  language: string;
  location?: string;
}

export interface FarmerProfile {
  farmer_id: string;
  user_id: string;
  land_area: number;
  soil_type?: string;
  preferred_crops?: string;
}

export interface ProfileUpsertRequest {
  user: UserProfile;
  farmer: FarmerProfile;
}

export interface ProfileResponse {
  user: UserProfile;
  farmer: FarmerProfile;
}

export interface PredictionHistoryItem {
  prediction_id: number;
  user_id: string;
  model_type: string;
  crop?: string;
  district: string;
  season: string;
  predicted_value: number;
  created_at: string;
}
