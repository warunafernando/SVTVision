import { describe, it, expect, vi, beforeEach } from 'vitest'
import { render, screen, waitFor, fireEvent, act } from '@testing-library/react'
import PipelineCanvas from './PipelineCanvas'

describe('PipelineCanvas', () => {
  beforeEach(() => {
    vi.clearAllMocks()
  })

  const defaultProps = {
    nodes: [] as any[],
    edges: [] as any[],
    layout: {} as Record<string, { x: number; y: number }>,
    selectedNodeId: null as string | null,
    onGraphChange: vi.fn(),
    onNodeSelect: vi.fn(),
  }

  it('shows empty hint when no nodes', () => {
    render(<PipelineCanvas {...defaultProps} />)
    expect(screen.getByText(/Drag nodes from the palette/)).toBeInTheDocument()
  })

  it.skip('creates node on drop from palette', async () => {
    const nodeData = {
      id: '',
      type: 'source' as const,
      source_type: 'camera',
      ports: { inputs: [], outputs: [{ name: 'frame', type: 'frame' }] },
    }
    const mockDataTransfer = {
      getData: (format: string) => (format === 'application/json' ? JSON.stringify(nodeData) : ''),
      dropEffect: '',
      effectAllowed: '',
    }
    render(<PipelineCanvas {...defaultProps} />)
    const dropzone = screen.getByTestId('vp-canvas-dropzone')
    const dropEvent = new Event('drop', { bubbles: true })
    Object.defineProperty(dropEvent, 'dataTransfer', { value: mockDataTransfer })
    Object.defineProperty(dropEvent, 'clientX', { value: 200 })
    Object.defineProperty(dropEvent, 'clientY', { value: 150 })
    fireEvent(dropzone, dropEvent)
    await waitFor(() => {
      expect(screen.getByText('camera')).toBeInTheDocument()
    })
  })

  it.skip('calls onGraphChange when nodes change', async () => {
    const onGraphChange = vi.fn()
    const nodeData = {
      id: '',
      type: 'source' as const,
      source_type: 'camera',
      ports: { inputs: [], outputs: [{ name: 'frame', type: 'frame' }] },
    }
    const mockDataTransfer = {
      getData: (format: string) => (format === 'application/json' ? JSON.stringify(nodeData) : ''),
      dropEffect: '',
      effectAllowed: '',
    }
    render(<PipelineCanvas {...defaultProps} onGraphChange={onGraphChange} />)
    const dropzone = screen.getByTestId('vp-canvas-dropzone')
    const dropEvent = new Event('drop', { bubbles: true })
    Object.defineProperty(dropEvent, 'dataTransfer', { value: mockDataTransfer })
    Object.defineProperty(dropEvent, 'clientX', { value: 200 })
    Object.defineProperty(dropEvent, 'clientY', { value: 150 })
    fireEvent(dropzone, dropEvent)
    await waitFor(() => {
      expect(onGraphChange).toHaveBeenCalled()
    })
  })
})
