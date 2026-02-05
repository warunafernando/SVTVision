/**
 * Stage algorithm schemas - variables per algorithm for vision pipeline stages.
 * Variables are saved per node (in node.config) when the pipeline is saved.
 */

export interface StageVariableSchema {
  key: string;
  label: string;
  type: 'number' | 'select' | 'boolean' | 'text';
  default: number | string | boolean;
  options?: { value: string | number; label: string }[];
  min?: number;
  max?: number;
}

export interface StageAlgorithmSchema {
  id: string;
  label: string;
  ports: { inputs: { name: string; type: string }[]; outputs: { name: string; type: string }[] };
  variables: StageVariableSchema[];
}

export const STAGE_ALGORITHM_SCHEMAS: StageAlgorithmSchema[] = [
  {
    id: 'preprocess_cpu',
    label: 'preprocess_cpu',
    ports: {
      inputs: [{ name: 'frame', type: 'frame' }],
      outputs: [{ name: 'frame', type: 'frame' }],
    },
    variables: [
      { key: 'blur_kernel_size', label: 'Blur kernel size', type: 'number', default: 3, min: 1, max: 21 },
      { key: 'threshold_type', label: 'Threshold type', type: 'select', default: 'adaptive', options: [
        { value: 'adaptive', label: 'Adaptive' },
        { value: 'binary', label: 'Binary' },
      ]},
      { key: 'adaptive_block_size', label: 'Adaptive block size', type: 'number', default: 15, min: 3, max: 51 },
      { key: 'adaptive_c', label: 'Adaptive C', type: 'number', default: 3, min: 0, max: 20 },
      { key: 'binary_threshold', label: 'Binary threshold', type: 'number', default: 127, min: 0, max: 255 },
      { key: 'morphology', label: 'Morphology', type: 'boolean', default: false },
      { key: 'morph_kernel_size', label: 'Morph kernel size', type: 'number', default: 3, min: 1, max: 15 },
    ],
  },
  {
    id: 'preprocess_gpu',
    label: 'Preprocess (GPU)',
    ports: {
      inputs: [{ name: 'frame', type: 'frame' }],
      outputs: [{ name: 'frame', type: 'frame' }],
    },
    variables: [
      { key: 'blur_kernel_size', label: 'Blur kernel size', type: 'number', default: 3, min: 1, max: 21 },
      { key: 'threshold_type', label: 'Threshold type', type: 'select', default: 'adaptive', options: [
        { value: 'adaptive', label: 'Adaptive' },
        { value: 'binary', label: 'Binary' },
      ]},
      { key: 'adaptive_block_size', label: 'Adaptive block size', type: 'number', default: 15, min: 3, max: 51 },
      { key: 'adaptive_c', label: 'Adaptive C', type: 'number', default: 3, min: 0, max: 20 },
      { key: 'binary_threshold', label: 'Binary threshold', type: 'number', default: 127, min: 0, max: 255 },
      { key: 'morphology', label: 'Morphology', type: 'boolean', default: false },
      { key: 'morph_kernel_size', label: 'Morph kernel size', type: 'number', default: 3, min: 1, max: 15 },
    ],
  },
  {
    id: 'detect_apriltag_cpu',
    label: 'detect_apriltag_cpu',
    ports: {
      inputs: [{ name: 'frame', type: 'frame' }],
      outputs: [{ name: 'frame', type: 'frame' }, { name: 'detections', type: 'detections' }],
    },
    variables: [
      { key: 'tag_family', label: 'Tag family', type: 'select', default: 'tag36h11', options: [
        { value: 'tag36h11', label: 'tag36h11' },
        { value: 'tag25h9', label: 'tag25h9' },
        { value: 'tag16h5', label: 'tag16h5' },
      ]},
    ],
  },
  {
    id: 'overlay_cpu',
    label: 'overlay_cpu',
    ports: {
      inputs: [
        { name: 'frame', type: 'frame' },
        { name: 'detections', type: 'detections' },
      ],
      outputs: [{ name: 'frame', type: 'frame' }],
    },
    variables: [],
  },
];

/** Custom stages from palette (localStorage) - merged at runtime */
export function getCustomStageSchemas(): StageAlgorithmSchema[] {
  try {
    const raw = localStorage.getItem('vp_custom_stages');
    const items = raw ? JSON.parse(raw) : [];
    return items.map((i: { id: string; label: string; stage_id?: string; ports?: { inputs: { name: string; type: string }[]; outputs: { name: string; type: string }[] } }) => ({
      id: i.stage_id ?? i.id,
      label: i.label,
      ports: i.ports ?? { inputs: [{ name: 'frame', type: 'frame' }], outputs: [{ name: 'frame', type: 'frame' }] },
      variables: [],
    }));
  } catch {
    return [];
  }
}

export function getAllStageAlgorithmSchemas(): StageAlgorithmSchema[] {
  return [...STAGE_ALGORITHM_SCHEMAS, ...getCustomStageSchemas()];
}

export function getStageAlgorithmSchema(stageId: string): StageAlgorithmSchema | undefined {
  return getAllStageAlgorithmSchemas().find((s) => s.id === stageId);
}

export function getDefaultConfigForAlgorithm(stageId: string): Record<string, unknown> {
  const schema = getStageAlgorithmSchema(stageId);
  if (!schema) return {};
  const config: Record<string, unknown> = {};
  for (const v of schema.variables) {
    config[v.key] = v.default;
  }
  return config;
}
