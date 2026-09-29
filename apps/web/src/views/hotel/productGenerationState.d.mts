export function primaryFromCandidate(candidate: any): any
export function promoteCandidate(primary: any, candidates: any[], key: string): { primary: any; candidates: any[] }
export function validationChangeNote(validationError: any, fallback?: string): string
export function prepareAdvisorResponse(currentAdvisor: any, previousPrimary: any, nextAdvisor: any): {
  advisor: any
  primary: any
  validationNote: string
}
export function primaryFromRefinedProduct(product: any, previousPrimary?: any): any
